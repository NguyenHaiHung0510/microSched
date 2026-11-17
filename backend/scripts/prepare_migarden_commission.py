"""Prepare a private, reviewed credential transaction; never connects during prepare.

Actual production apply is an Owner operation. Only the named one-Controller
binding is supported; there is no inventory, discovery or implicit replacement.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from cryptography import x509
from sqlalchemy.engine import make_url

from app.domain.migarden.credentials import TOKEN
from scripts.provision_migarden_qa import CHECKOUT, create_token_file

STATE_KEYS = {"device_id", "device_environment", "token_hash", "revoked_at"}
SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
HASH = re.compile(r"^[a-f0-9]{64}$")


def sql_text(value: str | None) -> str:
    return "NULL" if value is None else "'" + value.replace("'", "''") + "'"


def expected_state(value: dict, environment: str) -> dict:
    if set(value) != STATE_KEYS:
        raise ValueError("expected-state file has the wrong fields")
    result = dict(value)
    if result["device_id"] is not None and not SAFE_ID.fullmatch(result["device_id"]):
        raise ValueError("invalid old identity")
    if result["device_environment"] not in {None, environment}:
        raise ValueError("the binding belongs to a different environment")
    if result["token_hash"] is not None and not HASH.fullmatch(result["token_hash"]):
        raise ValueError("invalid old token digest")
    if (result["device_id"] is None) != (result["device_environment"] is None):
        raise ValueError("incomplete old credential environment")
    if (result["device_id"] is None) != (result["token_hash"] is None):
        raise ValueError("incomplete old credential")
    if result["revoked_at"] is not None:
        instant = datetime.fromisoformat(result["revoked_at"])
        if instant.utcoffset() is None:
            raise ValueError("revocation time must be timezone-aware")
        result["revoked_at"] = instant.isoformat()
    return result


def transaction(
    *,
    action: str,
    environment: str,
    device_id: str,
    database: str,
    expected: dict,
    token_hash: str | None,
    operation_id: str,
) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_]{1,63}", database):
        raise ValueError("database identifier must be explicit and bounded")
    old = expected_state(expected, environment)
    if environment not in {"qa", "production"} or action not in {"issue", "revoke"}:
        raise ValueError("invalid operation")
    if not SAFE_ID.fullmatch(device_id) or (
        environment == "production" and device_id.startswith("qa-")
    ):
        raise ValueError("invalid production identity")
    if old["device_id"] is not None and old["device_id"] != device_id:
        raise ValueError("replacement identity needs a separate reviewed recovery")
    if action == "issue" and old["token_hash"] is not None and old["revoked_at"] is None:
        raise ValueError("revoke the old credential before preparing a rotation")
    if action == "revoke" and (old["token_hash"] is None or old["revoked_at"] is not None):
        raise ValueError("revoke requires an active expected credential")
    if action == "issue" and (token_hash is None or not HASH.fullmatch(token_hash)):
        raise ValueError("invalid new digest")
    if not SAFE_ID.fullmatch(operation_id):
        raise ValueError("invalid operation identity")
    new_hash = token_hash if action == "issue" else old["token_hash"]
    audit = json.dumps(
        {
            "operation_id": operation_id,
            "zone_id": "zone-a",
            "binding_ref": "zone-a-v1",
            "device_id": device_id,
            "environment": environment,
            "old_token_hash": old["token_hash"],
            "new_token_hash": new_hash,
        },
        separators=(",", ":"),
    )
    guard = ""
    if action == "issue":
        guard = """
    IF z.unidentified_execution OR z.report_reconciliation IS NOT NULL OR EXISTS (
        SELECT 1 FROM microsched.migarden_command WHERE kind='start'
        AND status IN ('pending','received','granted','started','unknown')
    ) OR EXISTS (
        SELECT 1 FROM microsched.migarden_session WHERE outcome IS NULL OR outcome='unknown'
    ) THEN
        RAISE EXCEPTION 'unresolved execution or ingest: commission refused';
    END IF;"""
        update = (
            "device_id="
            + sql_text(device_id)
            + ", device_environment="
            + sql_text(environment)
            + ", token_hash="
            + sql_text(new_hash)
            + ", revoked_at=NULL"
        )
    else:
        update = "revoked_at=transaction_timestamp(), preview=NULL"
    return f"""BEGIN;
DO $commission$
DECLARE z microsched.migarden_zone%ROWTYPE;
BEGIN
    IF current_database() <> {sql_text(database)} OR current_user <> 'microsched_app' THEN
        RAISE EXCEPTION 'commission target or role mismatch';
    END IF;
    INSERT INTO microsched.migarden_zone(zone_id) VALUES ('zone-a')
        ON CONFLICT(zone_id) DO NOTHING;
    SELECT * INTO STRICT z FROM microsched.migarden_zone WHERE zone_id='zone-a' FOR UPDATE;
    IF z.device_id IS DISTINCT FROM {sql_text(old["device_id"])}
       OR z.device_environment IS DISTINCT FROM {sql_text(old["device_environment"])}
       OR z.token_hash IS DISTINCT FROM {sql_text(old["token_hash"])}
       OR z.revoked_at IS DISTINCT FROM {sql_text(old["revoked_at"])}::timestamptz THEN
        RAISE EXCEPTION 'commission CAS conflict: inspect fresh binding before retry';
    END IF;
    {guard}
    UPDATE microsched.migarden_zone SET {update} WHERE zone_id='zone-a';
    UPDATE microsched.migarden_command SET status='canceled', reason='credential_rebound'
        WHERE kind='start' AND status IN ('pending','received') AND grant_id IS NULL;
    INSERT INTO microsched.audit_log(trace_id,turn_id,action,tool,entity_type,entity_id,payload)
        VALUES(uuidv7(),uuidv7(),{sql_text("migarden.credential." + action)},
               'owner.commissioning','migarden_zone',z.id,{sql_text(audit)}::jsonb);
END $commission$;
COMMIT;
"""


def private_directory(raw: Path) -> Path:
    directory = raw.resolve()
    local = CHECKOUT / ".local"
    if not directory.is_relative_to(local) or local.resolve() != local or directory.exists():
        raise ValueError("choose a fresh directory below this worktree's .local")
    directory.mkdir(parents=True)
    return directory


def prepare(args) -> None:
    old = json.loads(args.expected_state_file.read_text(encoding="utf-8"))
    token = secrets.token_urlsafe(32) if args.operation == "issue" else None
    digest = hashlib.sha256(token.encode()).hexdigest() if token else None
    sql = transaction(
        action=args.operation,
        environment=args.environment,
        device_id=args.device_id,
        database=args.expected_database,
        expected=old,
        token_hash=digest,
        operation_id=secrets.token_hex(16),
    )
    directory = private_directory(args.output_dir)
    if token:
        create_token_file(directory / "device.token", token)
    create_token_file(directory / "binding.sql", sql)
    metadata = {
        "environment": args.environment,
        "device_id": args.device_id,
        "zone_id": "zone-a",
        "binding_ref": "zone-a-v1",
        "expected_host": args.expected_host,
        "expected_port": args.expected_port,
        "expected_database": args.expected_database,
        "operation": args.operation,
        "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        "device_token_sha256": digest,
    }
    # The writer appends exactly one newline; digest the saved bytes.
    metadata["sql_sha256"] = hashlib.sha256((directory / "binding.sql").read_bytes()).hexdigest()
    create_token_file(directory / "plan.json", json.dumps(metadata, indent=2))


def apply_plan(args) -> None:
    directory = args.plan_dir.resolve()
    if not directory.is_relative_to(CHECKOUT / ".local"):
        raise ValueError("plan must be below this checkout's .local")
    plan = json.loads((directory / "plan.json").read_text(encoding="ascii"))
    sql = (directory / "binding.sql").read_bytes()
    if hashlib.sha256(sql).hexdigest() != plan["sql_sha256"]:
        raise ValueError("reviewed SQL has changed")
    raw = os.environ.get("MIGARDEN_COMMISSION_DATABASE_URL", "")
    url = make_url(raw)
    if (
        url.drivername != "postgresql"
        or url.username != "microsched_app"
        or url.host != plan["expected_host"]
        or (url.port or 5432) != plan["expected_port"]
        or url.database != plan["expected_database"]
        or set(url.query) - {"sslmode", "channel_binding"}
    ):
        raise ValueError("explicit target differs from the reviewed plan")
    if plan["environment"] == "production" and (
        url.host in {"127.0.0.1", "localhost", "::1", "db", "host.docker.internal"}
        or url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}
    ):
        raise ValueError("production plan needs its distinct TLS-protected database")
    # No dotenv, app factory, redirect, discovery or shell interpolation.
    with psycopg.connect(raw, autocommit=True, connect_timeout=20) as connection:
        connection.execute(sql.decode("ascii"), prepare=False)


def profile(args) -> None:
    """Offline bridge to the firmware-owned mg-rel-v1/profile-v1 blob."""
    directory = args.plan_dir.resolve()
    if not directory.is_relative_to(CHECKOUT / ".local"):
        raise ValueError("profile must use a private plan below this checkout")
    network = json.loads(args.network_file.read_text(encoding="utf-8"))
    plan = json.loads((args.plan_dir / "plan.json").read_text(encoding="ascii"))
    token = (args.plan_dir / "device.token").read_text(encoding="ascii").strip()
    if (
        not TOKEN.fullmatch(token)
        or plan["environment"] != "production"
        or hashlib.sha256(token.encode()).hexdigest() != plan["device_token_sha256"]
    ):
        raise ValueError("use the exact production plan and token file")
    if set(network) != {"wifi_ssid", "wifi_password", "base_url", "ca_pem"}:
        raise ValueError("network file has the wrong fields")
    origin = urlsplit(network["base_url"])
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.path
        or origin.query
        or origin.fragment
    ):
        raise ValueError("profile needs an HTTPS origin without path")
    if origin.username or origin.password:
        raise ValueError("profile origin must not contain credentials")
    if not all(isinstance(value, str) for value in network.values()):
        raise ValueError("profile values must be strings")
    if (
        not 1 <= len(network["wifi_ssid"].encode("utf-8")) <= 32
        or not 8 <= len(network["wifi_password"].encode("utf-8")) <= 64
        or len(network["base_url"]) > 255
        or len(network["ca_pem"].encode("utf-8")) > 6144
        or "PRIVATE KEY" in network["ca_pem"]
    ):
        raise ValueError("profile fields exceed firmware bounds")
    certificate = x509.load_pem_x509_certificate(network["ca_pem"].encode("ascii"))
    if not certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("profile certificate must be a CA trust root")
    content = json.dumps(
        network
        | {
            "device_id": plan["device_id"],
            "device_token": token,
            "fixture_verified": args.fixture_verified,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(content.encode("utf-8")) > 8192:
        raise ValueError("profile exceeds firmware bounds")
    # UTF-8, no BOM. The firmware must validate the actual CA, origin and field bounds.
    destination = args.plan_dir.resolve() / "release-profile.json"
    if not destination.is_relative_to(CHECKOUT / ".local"):
        raise ValueError("profile output must stay in the private plan directory")
    # File ACL established while empty, before any network credential is written.
    create_token_file(destination, "")
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("prepare")
    build.add_argument("--operation", choices=["issue", "revoke"], required=True)
    build.add_argument("--environment", choices=["qa", "production"], required=True)
    build.add_argument("--device-id", required=True)
    build.add_argument("--expected-host", required=True)
    build.add_argument("--expected-port", type=int, default=5432)
    build.add_argument("--expected-database", required=True)
    build.add_argument("--expected-state-file", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    apply = sub.add_parser("apply")
    apply.add_argument("--plan-dir", type=Path, required=True)
    compose = sub.add_parser("profile")
    compose.add_argument("--plan-dir", type=Path, required=True)
    compose.add_argument("--network-file", type=Path, required=True)
    compose.add_argument("--fixture-verified", action="store_true")
    args = parser.parse_args()
    try:
        {"prepare": prepare, "apply": apply_plan, "profile": profile}[args.command](args)
    except Exception:
        raise SystemExit(
            "commission refused; verify the private plan and explicit target"
        ) from None
    print("commission_" + args.command + "=ok; no credential values printed")


if __name__ == "__main__":
    main()
