r"""Scrub and prepare a Neon ephemeral branch for microSched QA & Rehearsal.

Safely scrubs production data mirrored on a Neon branch:
  1. Total Format-Preserving Scrambling (length, markdown, CJK, Vietnamese)
  2. Re-encryption of private/always-encrypted columns with QA_ENCRYPTION_MASTER_KEY
  3. Wiping of semantic vector embeddings (note.embedding = NULL) and audit logs
  4. Resetting PIN to '123456' (Argon2) and clearing throttle
  5. Inserting a pre-seeded QA session token ('qa_token') for 'owner@test.local'
  6. Truncating push subscriptions & reminder dispatches (zero blast radius)
"""

import argparse
import asyncio
import base64
import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn
from app.core.private_pin import hash_pin
from app.core.scrambler import scramble_text
from app.core.settings import get_settings

CIPHERTEXT_PREFIX = "enc:v1:"
_NONCE_BYTES = 12


def _decrypt_value(key_bytes: bytes, ciphertext: str) -> str:
    """Decrypt a string with prefix enc:v1: using the given key."""
    if not ciphertext or not ciphertext.startswith(CIPHERTEXT_PREFIX):
        return ciphertext
    cipher = AESGCM(key_bytes)
    payload = base64.urlsafe_b64decode(ciphertext[len(CIPHERTEXT_PREFIX) :])
    nonce = payload[:_NONCE_BYTES]
    encrypted = payload[_NONCE_BYTES:]
    plaintext_bytes = cipher.decrypt(nonce, encrypted, None)
    return plaintext_bytes.decode("utf-8")


def _decrypt_or_synthesize(key_bytes: bytes, ciphertext: str, salt: str) -> str:
    """Decrypt and scramble, or synthesize format-preserving text if key differs."""
    if not ciphertext:
        return ciphertext
    if not ciphertext.startswith(CIPHERTEXT_PREFIX):
        return scramble_text(ciphertext, salt)
    try:
        plain = _decrypt_value(key_bytes, ciphertext)
        return scramble_text(plain, salt)
    except Exception:
        # Prod key unavailable locally: synthesize exact-length text
        try:
            payload = base64.urlsafe_b64decode(ciphertext[len(CIPHERTEXT_PREFIX) :])
            target_len = max(1, len(payload) - 28)
        except Exception:
            target_len = 16
        base_words = [
            "Ghi",
            "chú",
            "công",
            "việc",
            "kế",
            "hoạch",
            "tháng",
            "chi",
            "tiêu",
            "khoản",
            "mục",
            "mẫu",
        ]
        res = []
        curr = 0
        idx = int(hashlib.md5((ciphertext + salt).encode()).hexdigest(), 16) % len(base_words)
        while curr < target_len:
            word = base_words[idx % len(base_words)]
            if curr + len(word) <= target_len:
                res.append(word)
                curr += len(word)
                if curr < target_len:
                    res.append(" ")
                    curr += 1
            else:
                rem = target_len - curr
                res.append("a" * rem)
                curr += rem
            idx += 1
        return "".join(res)


def _encrypt_value(key_bytes: bytes, plaintext: str) -> str:
    """Encrypt a plaintext string with AES-GCM and format as enc:v1:..."""
    cipher = AESGCM(key_bytes)
    nonce = os.urandom(_NONCE_BYTES)
    encrypted = cipher.encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = nonce + encrypted
    return CIPHERTEXT_PREFIX + base64.urlsafe_b64encode(payload).decode("ascii")


async def scrub_branch_data(
    dsn: str,
    prod_key_b64: str,
    qa_key_b64: str | None = None,
    test_pin: str = "123456",
    salt: str = "microsched_qa_salt",
) -> dict[str, int]:
    """Scrub all personal data and re-encrypt private data on the QA branch."""
    prod_key = base64.urlsafe_b64decode(prod_key_b64)
    if qa_key_b64:
        qa_key = base64.urlsafe_b64decode(qa_key_b64)
    else:
        qa_key = prod_key

    conn = await asyncpg.connect(dsn, timeout=30)
    counts: dict[str, int] = {}

    try:
        async with conn.transaction():
            await conn.execute("SET microsched.task_due_writer = 'v2'")

            # 1. Scramble Tasks
            tasks = await conn.fetch("SELECT id, title, body_md, is_private FROM microsched.task")
            counts["tasks"] = len(tasks)
            for t in tasks:
                t_id = t["id"]
                t_title = t["title"]
                t_body = t["body_md"]
                is_priv = t["is_private"]
                if is_priv:
                    new_title = _encrypt_value(
                        qa_key, _decrypt_or_synthesize(prod_key, t_title, salt)
                    )
                    new_body = (
                        _encrypt_value(qa_key, _decrypt_or_synthesize(prod_key, t_body, salt))
                        if t_body
                        else None
                    )
                else:
                    new_title = scramble_text(t_title, salt)
                    new_body = scramble_text(t_body, salt) if t_body else None
                await conn.execute(
                    "UPDATE microsched.task SET title = $1, body_md = $2 WHERE id = $3",
                    new_title,
                    new_body,
                    t_id,
                )

            # 2. Scramble Task Items
            task_items = await conn.fetch(
                "SELECT ti.id, ti.content, t.is_private "
                "FROM microsched.task_item ti JOIN microsched.task t ON ti.task_id = t.id"
            )
            counts["task_items"] = len(task_items)
            for ti in task_items:
                ti_id = ti["id"]
                content_raw = ti["content"]
                is_priv = ti["is_private"]
                if is_priv:
                    new_content = _encrypt_value(
                        qa_key, _decrypt_or_synthesize(prod_key, content_raw, salt)
                    )
                else:
                    new_content = scramble_text(content_raw, salt)
                await conn.execute(
                    "UPDATE microsched.task_item SET content = $1 WHERE id = $2",
                    new_content,
                    ti_id,
                )

            # 3. Scramble Notes & Clear Vectors
            notes = await conn.fetch("SELECT id, title, body_md, is_private FROM microsched.note")
            counts["notes"] = len(notes)
            for n in notes:
                n_id = n["id"]
                n_title = n["title"]
                n_body = n["body_md"]
                is_priv = n["is_private"]
                if is_priv:
                    new_title = _encrypt_value(
                        qa_key, _decrypt_or_synthesize(prod_key, n_title, salt)
                    )
                    new_body = (
                        _encrypt_value(qa_key, _decrypt_or_synthesize(prod_key, n_body, salt))
                        if n_body
                        else None
                    )
                else:
                    new_title = scramble_text(n_title, salt)
                    new_body = scramble_text(n_body, salt) if n_body else None
                note_sql = (
                    "UPDATE microsched.note "
                    "SET title = $1, body_md = $2, embedding = NULL WHERE id = $3"
                )
                await conn.execute(note_sql, new_title, new_body, n_id)

            # 4. Scramble Note Items
            note_items = await conn.fetch("SELECT id, content FROM microsched.note_item")
            counts["note_items"] = len(note_items)
            for ni in note_items:
                new_content = scramble_text(ni["content"], salt)
                await conn.execute(
                    "UPDATE microsched.note_item SET content = $1 WHERE id = $2",
                    new_content,
                    ni["id"],
                )

            # 5. Scramble Trackers & Tracker Groups
            tr_groups = await conn.fetch("SELECT id, name FROM microsched.tracker_group")
            counts["tracker_groups"] = len(tr_groups)
            for tg in tr_groups:
                new_tg_name = scramble_text(tg["name"], salt)
                await conn.execute(
                    "UPDATE microsched.tracker_group SET name = $1 WHERE id = $2",
                    new_tg_name,
                    tg["id"],
                )

            trackers = await conn.fetch("SELECT id, name, reminder_text FROM microsched.tracker")
            counts["trackers"] = len(trackers)
            for tr in trackers:
                new_name = _encrypt_value(
                    qa_key, _decrypt_or_synthesize(prod_key, tr["name"], salt)
                )
                rem_text = scramble_text(tr["reminder_text"], salt) if tr["reminder_text"] else None
                await conn.execute(
                    "UPDATE microsched.tracker SET name = $1, reminder_text = $2 WHERE id = $3",
                    new_name,
                    rem_text,
                    tr["id"],
                )

            # 6. Scramble Subscriptions & Entries
            subs = await conn.fetch(
                "SELECT id, name, amount, list_amount, note_md FROM microsched.subscription"
            )
            counts["subscriptions"] = len(subs)
            for s in subs:
                s_name = _encrypt_value(qa_key, _decrypt_or_synthesize(prod_key, s["name"], salt))
                s_amt = _encrypt_value(qa_key, _decrypt_or_synthesize(prod_key, s["amount"], salt))
                s_list = (
                    _encrypt_value(qa_key, _decrypt_or_synthesize(prod_key, s["list_amount"], salt))
                    if s["list_amount"]
                    else None
                )
                s_note = (
                    _encrypt_value(qa_key, _decrypt_or_synthesize(prod_key, s["note_md"], salt))
                    if s["note_md"]
                    else None
                )
                sub_sql = (
                    "UPDATE microsched.subscription "
                    "SET name = $1, amount = $2, list_amount = $3, note_md = $4 WHERE id = $5"
                )
                await conn.execute(sub_sql, s_name, s_amt, s_list, s_note, s["id"])

            entries = await conn.fetch(
                "SELECT id, amount, list_amount, note_md FROM microsched.entry"
            )
            counts["entries"] = len(entries)
            for e in entries:
                e_amt = (
                    _encrypt_value(qa_key, _decrypt_or_synthesize(prod_key, e["amount"], salt))
                    if e["amount"]
                    else None
                )
                e_list = (
                    _encrypt_value(qa_key, _decrypt_or_synthesize(prod_key, e["list_amount"], salt))
                    if e["list_amount"]
                    else None
                )
                e_note = (
                    _encrypt_value(qa_key, _decrypt_or_synthesize(prod_key, e["note_md"], salt))
                    if e["note_md"]
                    else None
                )
                entry_sql = (
                    "UPDATE microsched.entry "
                    "SET amount = $1, list_amount = $2, note_md = $3 WHERE id = $4"
                )
                await conn.execute(entry_sql, e_amt, e_list, e_note, e["id"])

            # 7. Scramble Calendar & Day Annotations
            sources = await conn.fetch("SELECT id, name FROM microsched.calendar_source")
            counts["calendar_sources"] = len(sources)
            for src in sources:
                s_name = scramble_text(src["name"], salt)
                await conn.execute(
                    "UPDATE microsched.calendar_source SET name = $1 WHERE id = $2",
                    s_name,
                    src["id"],
                )

            cal_events = await conn.fetch(
                "SELECT id, title, description_md, location FROM microsched.calendar_event"
            )
            counts["calendar_events"] = len(cal_events)
            for ce in cal_events:
                c_title = scramble_text(ce["title"], salt)
                c_desc = scramble_text(ce["description_md"], salt) if ce["description_md"] else None
                c_loc = scramble_text(ce["location"], salt) if ce["location"] else None
                ev_sql = (
                    "UPDATE microsched.calendar_event "
                    "SET title = $1, description_md = $2, location = $3 WHERE id = $4"
                )
                await conn.execute(ev_sql, c_title, c_desc, c_loc, ce["id"])

            day_annots = await conn.fetch(
                "SELECT id, label, note_md FROM microsched.day_annotation"
            )
            counts["day_annotations"] = len(day_annots)
            for da in day_annots:
                d_label = scramble_text(da["label"], salt)
                d_note = scramble_text(da["note_md"], salt) if da["note_md"] else None
                await conn.execute(
                    "UPDATE microsched.day_annotation SET label = $1, note_md = $2 WHERE id = $3",
                    d_label,
                    d_note,
                    da["id"],
                )

            # 8. Truncate Audit Logs & Push Subscriptions (Zero blast radius)
            trunc_sql = (
                "TRUNCATE TABLE microsched.audit_log, microsched.push_subscription, "
                "microsched.reminder_dispatch, microsched.session"
            )
            await conn.execute(trunc_sql)

            # 9. Set PIN to 123456 & reset throttle
            pin_hash = hash_pin(test_pin)
            await conn.execute(
                "INSERT INTO microsched.app_setting (key, value) "
                "VALUES ('private_pin', $1::jsonb) "
                "ON CONFLICT (key) DO UPDATE SET value = $1::jsonb",
                f'{{"hash": "{pin_hash}", "bootstrap": false}}',
            )
            await conn.execute(
                "DELETE FROM microsched.app_setting WHERE key = 'private_unlock_throttle'"
            )

            # 10. Inject Pre-seeded QA Session Token (token: 'qa_token')
            now = datetime.now(UTC)
            qa_token_hash = hashlib.sha256(b"qa_token").hexdigest()
            sess_sql = (
                "INSERT INTO microsched.session "
                "(id, token_hash, user_email, last_seen_at, expires_at, created_at, updated_at) "
                "VALUES ($1, $2, 'owner@test.local', $3, $4, $3, $3)"
            )
            await conn.execute(
                sess_sql,
                uuid4(),
                qa_token_hash,
                now,
                now + timedelta(days=30),
            )

    finally:
        await conn.close()

    return counts


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Prepare Neon QA branch with format-preserving scrambled data."
    )
    parser.add_argument(
        "--branch-url",
        default=(
            settings.neon_develop_branch_key
            or os.environ.get("NEON_DEVELOP_BRANCH_KEY")
            or os.environ.get("DATABASE_URL_DEVELOP")
        ),
        help="Connection URL to the target Neon QA branch",
    )
    parser.add_argument(
        "--prod-key",
        default=(
            settings.encryption_master_key
            or os.environ.get("ENCRYPTION_MASTER_KEY")
            or os.environ.get("PROD_KEY")
        ),
        help="Production master key (base64) to decrypt existing ciphertext",
    )
    parser.add_argument(
        "--qa-key",
        default=os.environ.get("QA_ENCRYPTION_MASTER_KEY"),
        help="QA master key (base64) for re-encrypting",
    )
    parser.add_argument("--pin", default="123456", help="Test PIN to set for private unlock")
    parser.add_argument(
        "--salt", default="microsched_qa_salt", help="Salt for deterministic scrambling"
    )
    args = parser.parse_args()

    if not args.branch_url:
        raise ValueError(
            "Missing branch URL (pass --branch-url or set NEON_DEVELOP_BRANCH_KEY in environment)"
        )
    if not args.prod_key:
        raise ValueError(
            "Missing production master key (pass --prod-key or set ENCRYPTION_MASTER_KEY)"
        )

    host = (make_url(args.branch_url).host or "").lower()
    # Fail-closed guard for a destructive script (it truncates session/audit/
    # push tables): the host must be the declared develop branch. The raw
    # DATABASE_URL env var is the production reference on purpose: in local
    # mode Settings redirects database_url to the develop branch, so comparing
    # against settings.database_url here would compare develop with itself.
    raw_database_url = os.environ.get("DATABASE_URL")
    prod_host = (make_url(raw_database_url).host or "").lower() if raw_database_url else ""
    if prod_host and host == prod_host:
        raise ValueError(f"CRITICAL SAFETY VIOLATION: refusing to scrub production host {host!r}.")
    if "prod" in host:
        raise ValueError(f"Refusing to run data scrubbing on host containing 'prod': {host!r}.")
    declared_dev = settings.neon_develop_branch_key
    declared_dev_host = (make_url(declared_dev).host or "").lower() if declared_dev else ""
    if not declared_dev_host or host != declared_dev_host:
        raise ValueError(
            "Host is not the declared NEON_DEVELOP_BRANCH_KEY target; pass --branch-url "
            "pointing at the declared develop branch."
        )

    print(f"Starting data scrubbing on target branch host: {host}...")
    res = asyncio.run(
        scrub_branch_data(
            dsn=asyncpg_dsn(args.branch_url),
            prod_key_b64=args.prod_key,
            qa_key_b64=args.qa_key,
            test_pin=args.pin,
            salt=args.salt,
        )
    )
    print("Data scrubbing completed successfully! Counts summary:")
    for k, v in res.items():
        print(f"  - {k}: {v}")
    print("Pre-seeded QA Session cookie: ms_session=qa_token (user: owner@test.local, PIN: 123456)")


if __name__ == "__main__":
    main()
