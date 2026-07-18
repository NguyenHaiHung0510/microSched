"""Read-only inventory of the OLD microSched stores (SQLite v1 + Postgres v2).

Dùng để: xác định nguồn-sự-thật và verify lại trước/sau cutover.
AN TOÀN: SQLite được COPY ra file tạm rồi mở read-only; Postgres bị ép
session read-only; chỉ chạy SELECT. Không ghi bất cứ gì vào store cũ.

Chạy:
    set PGPW=<postgres_password>        # KHÔNG hardcode password vào file
    python inventory_old_stores.py
"""
import sqlite3, shutil, os, sys, tempfile, datetime

SQLITE_SRC = r"C:\Users\os\Desktop\Tools\VC_microSchedule_home\todo.db"
PG_HOST, PG_PORT, PG_USER = "localhost", 5432, "postgres"

def inventory_sqlite():
    print("=" * 60, "\nSQLite  todo.db  (legacy v1)\n", "=" * 60, sep="")
    if not os.path.exists(SQLITE_SRC):
        print("  (không tìm thấy file)"); return
    mt = datetime.datetime.fromtimestamp(os.path.getmtime(SQLITE_SRC))
    print(f"live file last-modified: {mt}   size: {os.path.getsize(SQLITE_SRC):,} bytes")
    copy = os.path.join(tempfile.gettempdir(), "todo_copy_readonly.db")
    shutil.copy2(SQLITE_SRC, copy)
    try:
        con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        cur = con.cursor()
        for t in ["tasks", "subtasks", "schedule", "settings"]:
            n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            extra = ""
            if t in ("tasks", "schedule"):
                lo, hi = cur.execute(f"SELECT MIN(date_str), MAX(date_str) FROM {t}").fetchone()
                extra = f"   date_str: {lo} .. {hi}"
            print(f"  {t:10}: {n:5} rows{extra}")
        con.close()
    finally:
        try: os.remove(copy)
        except OSError: pass

def inventory_postgres():
    print("\n" + "=" * 60, "\nPostgreSQL  (v2, read-only)\n", "=" * 60, sep="")
    try:
        import psycopg
    except ImportError as e:
        print("psycopg không có:", e); return
    pw = os.environ.get("PGPW", "")
    base = f"postgresql://{PG_USER}:{pw}@{PG_HOST}:{PG_PORT}"
    ro = "-c default_transaction_read_only=on"
    with psycopg.connect(base + "/postgres", options=ro, autocommit=True) as c:
        dbs = [r[0] for r in c.execute(
            "SELECT datname FROM pg_database WHERE datistemplate=false").fetchall()]
    targets = [d for d in dbs if "microsched" in d.lower() or "schedule" in d.lower()]
    for db in targets:
        print(f"\n--- {db} ---")
        with psycopg.connect(base + f"/{db}", options=ro, autocommit=True) as c:
            tbls = [r[0] for r in c.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name").fetchall()]
            for t in tbls:
                cols = [r[0] for r in c.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=%s", (t,)).fetchall()]
                ts = "updated_at" if "updated_at" in cols else ("created_at" if "created_at" in cols else None)
                n = c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                mx = c.execute(f'SELECT MAX("{ts}") FROM "{t}"').fetchone()[0] if ts else None
                print(f"  {t:24}: {n:5} rows" + (f"   latest {ts}={mx}" if ts else ""))

if __name__ == "__main__":
    inventory_sqlite()
    inventory_postgres()
