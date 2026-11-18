"""Issue or revoke the local N01 Controller credential without logging secrets."""

import argparse
import asyncio
import csv
import os
import re
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database_urls import async_postgres_url
from app.core.settings import Settings
from app.domain.migarden.commands import expire_or_cancel, waiting_start
from app.domain.migarden.credentials import digest
from app.domain.migarden.storage import lock_zone

CHECKOUT = Path(__file__).resolve().parents[2]
QA_ID = re.compile(r"qa-[a-z0-9][a-z0-9-]{0,62}")
QA_DB = re.compile(r"microsched_n01_[a-z0-9_]+")


def check_target() -> URL:
    # Read the explicit process input first; never fall back to app dotenv for provisioning.
    url = make_url(async_postgres_url(os.environ.get("DATABASE_URL", "")))
    if (
        os.environ.get("APP_ENV") != "local"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not QA_DB.fullmatch(url.database or "")
        or bool(url.query)
    ):
        raise ValueError("explicit local N01 database required")
    return url


def get_sessionmaker(target: URL):
    # Dedicated factory, never the app's cached engine or dotenv-derived settings.
    return async_sessionmaker(create_async_engine(target), expire_on_commit=False)


def checked_factory():
    target = check_target()
    settings = Settings(_env_file=None)
    effective = make_url(settings.database_url) if settings.database_url else None
    if settings.is_production or effective != target:
        raise ValueError("resolved settings differ from the explicit local N01 target")
    factory = get_sessionmaker(target)
    engine = factory.kw.get("bind") if factory is not None else None
    if engine is None or engine.url != target:
        raise ValueError("resolved factory differs from the explicit local N01 target")
    return factory


def check_path(candidate: Path) -> Path:
    local = CHECKOUT / ".local"
    target = candidate.resolve()
    if not target.is_relative_to(local) or local.resolve() != local or target.suffix != ".token":
        raise ValueError("output must be a fresh .token file below this worktree's .local")
    return target


def restrict_windows(path: Path) -> None:
    sid = next(
        csv.reader(
            [
                subprocess.check_output(
                    ["whoami", "/user", "/fo", "csv", "/nh"],
                    text=True,
                ).strip()
            ]
        )
    )[1]
    if not re.fullmatch(r"S-[0-9-]+", sid):
        raise ValueError("could not determine the operator's Windows SID")
    subprocess.run(
        ["icacls", str(path), "/grant:r", f"*{sid}:(F)", "/inheritance:r"],
        check=True,
        capture_output=True,
    )


def create_token_file(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
            if os.name == "nt":
                restrict_windows(path)
            stream.write(token + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


async def apply(action: str, device_id: str, path: Path | None) -> None:
    factory = checked_factory()
    if not QA_ID.fullmatch(device_id):
        raise ValueError("local qa-* device identity required")
    created = False
    try:
        async with factory() as db, db.begin():
            zone = await lock_zone(db, create=action == "issue")
            if zone.device_id is not None and (
                zone.device_environment != "qa" or zone.device_id != device_id
            ):
                raise ValueError("a different device identity owns the binding")
            if action == "revoke":
                if zone.device_id != device_id:
                    raise ValueError("device not provisioned")
                zone.revoked_at = zone.revoked_at or datetime.now(UTC)
                zone.preview = None
                pending = await waiting_start(db)
                if pending is not None:
                    expire_or_cancel(pending, zone.revoked_at, cancel="controller_revoked")
                return
            if zone.token_hash is not None and zone.revoked_at is None:
                raise ValueError("revoke the current QA credential before rotating")
            assert path is not None
            token = secrets.token_urlsafe(32)
            create_token_file(path, token)
            created = True
            zone.device_id = device_id
            zone.device_environment = "qa"
            zone.token_hash = digest(token)
            zone.revoked_at = None
    except BaseException:
        if created and path is not None:
            path.unlink(missing_ok=True)
        raise
    finally:
        await factory.kw["bind"].dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("issue", "revoke"):
        command = sub.add_parser(action)
        command.add_argument("--device-id", required=True)
        if action == "issue":
            command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        path = check_path(args.output) if args.action == "issue" else None
        asyncio.run(apply(args.action, args.device_id, path))
    except Exception:
        # Driver/OS errors may contain DSNs, file paths, or SQL inputs.
        raise SystemExit(
            "N01 provision refused or failed; check the local binding, migration and output path"
        ) from None
    print("migarden_qa_credential=" + ("issued" if args.action == "issue" else "revoked"))


if __name__ == "__main__":
    main()
