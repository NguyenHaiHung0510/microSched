"""Fail-closed policy primitives for the QA025 disposable production cell.

This module deliberately has no Docker or Git subprocess calls.  The command
envelope is the only process seam; keeping the policy pure makes it possible to
prove denials without contacting a daemon.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

RUN_ID_RE = re.compile(r"^msqa025-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}$")
FIXTURE_PREFIX_RE = re.compile(
    r"^\[QA025:(msqa025-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8})\]$"
)
FIXTURE_LABEL_RE = re.compile(
    r"^\[QA025:(msqa025-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8})\](?: .+)?$"
)
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SERVICES = ("db", "bootstrap", "migrate", "seed", "app", "browser")
PASS_PHASES = (
    "preflight",
    "build",
    "database",
    "bootstrap",
    "migrate",
    "seed",
    "app_ready",
    "browser",
    "cleanup",
)

STATUS_EXIT_CODES = {
    "PASS": 0,
    "FAIL_ASSERTION": 20,
    "BLOCKED_PREREQUISITE": 30,
    "GUARD_DENIED": 40,
    "CLEANUP_GUARD_DENIED": 41,
    "SETUP_TIMEOUT": 50,
    "TEST_TIMEOUT": 51,
    "CLEANUP_TIMEOUT": 52,
    "INFRA_ERROR": 60,
}

APP_DATA_DENIED = frozenset(
    {
        "DATABASE_URL",
        "NEON_OWNER_URL",
        "NEON_MIGRATOR_URL",
        "CUTOVER_MIGRATOR_URL",
        "ALLOW_REMOTE_PG_TESTS",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "ALLOWED_EMAILS",
        "PRIVATE_PIN_BOOTSTRAP",
        "VAPID_PRIVATE_KEY",
        "VAPID_PUBLIC_KEY",
        "VAPID_CLAIMS_SUB",
        "FLY_API_TOKEN",
        "FLY_APP",
        "PLAYWRIGHT_BASE_URL",
    }
)

EXACT_PARENT_DENIED = APP_DATA_DENIED | frozenset(
    {
        "CDPATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "XDG_CONFIG_HOME",
    }
)

DENIED_PREFIXES = (
    "DOCKER_",
    "BUILDX_",
    "BUILDKIT_",
    "COMPOSE_",
    "GIT_",
)

HTTP_URL_RE = re.compile(r"https?://[^\s'\";]+", re.IGNORECASE)
DATABASE_URL_RE = re.compile(r"postgres(?:ql)?://", re.IGNORECASE)
PRODUCTION_HOST_RE = re.compile(
    r"(?:^|[./])(?:neon\.tech|fly\.dev)(?:$|[:/])", re.IGNORECASE
)


class CellError(RuntimeError):
    """One canonical runner failure with a stable machine status and exit code."""

    def __init__(self, status: str, message: str) -> None:
        if status not in STATUS_EXIT_CODES:
            raise ValueError(f"unsupported final status: {status}")
        super().__init__(message)
        self.status = status
        self.exit_code = STATUS_EXIT_CODES[status]


class GuardDenied(CellError):
    """A caller or target violated the production-default-deny boundary."""

    def __init__(self, message: str) -> None:
        super().__init__("GUARD_DENIED", message)


class CleanupGuardDenied(CellError):
    """Cleanup cannot safely prove it still targets the original local run."""

    def __init__(self, message: str) -> None:
        super().__init__("CLEANUP_GUARD_DENIED", message)


class BlockedPrerequisite(CellError):
    """A required local executable, daemon, Compose plugin, or browser is absent."""

    def __init__(self, message: str) -> None:
        super().__init__("BLOCKED_PREREQUISITE", message)


class AssertionFailure(CellError):
    """The real stack ran but an acceptance assertion was false."""

    def __init__(self, message: str) -> None:
        super().__init__("FAIL_ASSERTION", message)


def canonical_json(value: Any) -> bytes:
    """Serialize one hash-bound object with the QA025 canonical JSON rules."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def environment_key_hash(environment: Mapping[str, str]) -> str:
    keys = sorted(key.upper() if os.name == "nt" else key for key in environment)
    return sha256_bytes(canonical_json(keys))


def denied_parent_variable_names(environment: Mapping[str, str]) -> list[str]:
    """Return forbidden *names* without reading or rendering their values."""

    rejected: set[str] = set()
    for original_name in environment:
        name = original_name.upper()
        if (
            name in EXACT_PARENT_DENIED
            or name.startswith(DENIED_PREFIXES)
            or name.endswith("_PROXY")
            or name == "PROXY"
        ):
            rejected.add(name)
    return sorted(rejected)


def guard_parent_environment(environment: Mapping[str, str]) -> None:
    rejected = denied_parent_variable_names(environment)
    if rejected:
        raise GuardDenied("rejected parent variable names: " + ",".join(rejected))


def _windows_reparse_point(path: Path) -> bool:
    if os.name != "nt":
        return path.is_symlink()
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def validate_local_directory(path: Path, *, label: str) -> Path:
    """Accept only an existing absolute local directory with no reparse hop."""

    if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
        raise GuardDenied(f"{label} must be an absolute local path")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise GuardDenied(f"{label} is not an existing local directory") from error
    if not resolved.is_dir():
        raise GuardDenied(f"{label} is not a directory")
    current = Path(resolved.anchor)
    for part in resolved.parts[1:]:
        current /= part
        if _windows_reparse_point(current):
            raise GuardDenied(f"{label} traverses a symlink or reparse point")
    return resolved


def validate_owned_file(path: Path, *, roots: Sequence[Path], label: str) -> Path:
    """Require a regular, non-link file below one of the runner-owned roots."""

    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise GuardDenied(f"{label} does not exist") from error
    if (
        not resolved.is_file()
        or resolved.is_symlink()
        or _windows_reparse_point(resolved)
    ):
        raise GuardDenied(f"{label} must be a regular non-link file")
    allowed = False
    for root in roots:
        try:
            resolved.relative_to(root.resolve(strict=True))
        except ValueError:
            continue
        else:
            allowed = True
            break
    if not allowed:
        raise GuardDenied(f"{label} is outside the owned QA roots")
    return resolved


def assert_sha40(value: str, *, label: str = "git_sha") -> str:
    if SHA40_RE.fullmatch(value) is None:
        raise GuardDenied(f"{label} must be 40 lowercase hexadecimal characters")
    return value


def validate_run_id(value: str, *, label: str = "run_id") -> str:
    """Accept only the canonical lowercase QA025 identity.

    The lowercase separators are intentional protocol bytes, not a display
    convention.  Do not coerce a historical uppercase receipt into this
    schema-v1 contract.
    """

    if not isinstance(value, str) or RUN_ID_RE.fullmatch(value) is None:
        raise GuardDenied(
            f"{label} must match the canonical lowercase QA025 run_id grammar"
        )
    return value


def fixture_label_ledger(run_id: str) -> tuple[str, ...]:
    """Return every synthetic label the browser fixture may persist.

    This ledger remains run-local rather than becoming a receipt field: the
    receipt deliberately keeps only its compact prefix.  It is nevertheless a
    preflight contract because every future subprocess relies on these labels.
    """

    canonical = validate_run_id(run_id)
    prefix = f"[QA025:{canonical}]"
    return (
        f"{prefix} denied-private",
        f"{prefix} denied-item",
        f"{prefix} public-task",
        f"{prefix} private-task",
        f"{prefix} public-note",
        f"{prefix} public-item",
        f"{prefix} private-item",
        f"{prefix} note-item",
        f"{prefix} synthetic body",
    )


def _exact_utf8_equal(expected: str, actual: str, *, label: str) -> None:
    if not isinstance(actual, str) or actual.encode("utf-8") != expected.encode("utf-8"):
        raise GuardDenied(f"{label} must match run_id byte-for-byte")


def parse_fixture_prefix(prefix: str) -> str:
    """Extract the exact ID from the compact receipt fixture wrapper."""

    if not isinstance(prefix, str):
        raise GuardDenied("fixtures.prefix must be a string")
    match = FIXTURE_PREFIX_RE.fullmatch(prefix)
    if match is None:
        raise GuardDenied("fixtures.prefix must contain a canonical lowercase run_id")
    return match.group(1)


def parse_fixture_label(label: str) -> str:
    """Extract the exact ID carried by one fixture-ledger entry."""

    if not isinstance(label, str):
        raise GuardDenied("fixture label ledger entry must be a string")
    match = FIXTURE_LABEL_RE.fullmatch(label)
    if match is None:
        raise GuardDenied(
            "fixture label ledger entry must contain a canonical lowercase run_id"
        )
    return match.group(1)


def validate_fixture_identity_bindings(
    *,
    run_id: str,
    project_name: str,
    cleanup_run_id: str,
    cleanup_project_name: str,
    fixture_prefix: str,
    fixture_labels: Sequence[str],
) -> None:
    """Bind all run identity copies before filesystem or process side effects.

    Regex checks establish grammar only.  The raw UTF-8 comparisons below are
    the fail-closed proof that a valid-but-different lowercase M27 fixture ID
    cannot target the candidate cell.
    """

    canonical = validate_run_id(run_id)
    for label, value in (
        ("compose.project_name", project_name),
        ("cleanup.run_id", cleanup_run_id),
        ("cleanup.project_name", cleanup_project_name),
    ):
        validate_run_id(value, label=label)
        _exact_utf8_equal(canonical, value, label=label)
    _exact_utf8_equal(
        canonical,
        parse_fixture_prefix(fixture_prefix),
        label="fixtures.prefix run_id",
    )
    if not fixture_labels:
        raise GuardDenied("fixture label ledger must not be empty")
    for index, fixture_label in enumerate(fixture_labels):
        _exact_utf8_equal(
            canonical,
            parse_fixture_label(fixture_label),
            label=f"fixture label ledger entry {index}",
        )


def _service_network_names(service: Mapping[str, Any]) -> set[str]:
    networks = service.get("networks")
    if isinstance(networks, list):
        return {str(name) for name in networks}
    if isinstance(networks, dict):
        return {str(name) for name in networks}
    return set()


def _environment_map(service: Mapping[str, Any]) -> dict[str, str]:
    environment = service.get("environment", {})
    if isinstance(environment, dict):
        return {str(key): str(value) for key, value in environment.items()}
    if isinstance(environment, list):
        result: dict[str, str] = {}
        for entry in environment:
            key, separator, value = str(entry).partition("=")
            result[key] = value if separator else ""
        return result
    return {}


def _assert_no_forbidden_config_target(value: Any) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _assert_no_forbidden_config_target(child)
        return
    if isinstance(value, list):
        for child in value:
            _assert_no_forbidden_config_target(child)
        return
    if not isinstance(value, str):
        return
    if DATABASE_URL_RE.search(value) or PRODUCTION_HOST_RE.search(value):
        raise GuardDenied("rendered Compose contains a forbidden target literal")
    for match in HTTP_URL_RE.finditer(value):
        if urlsplit(match.group(0)).hostname != "127.0.0.1":
            raise GuardDenied("rendered Compose contains a non-loopback HTTP target")


def validate_compose_config(config: Mapping[str, Any]) -> None:
    """Validate the rendered Compose object before any resource is created."""

    _assert_no_forbidden_config_target(config)
    services = config.get("services")
    networks = config.get("networks")
    if not isinstance(services, dict) or set(services) != set(SERVICES):
        raise GuardDenied(
            "rendered Compose services must be exactly the QA025 service set"
        )
    if not isinstance(networks, dict) or set(networks) != {"cell"}:
        raise GuardDenied("rendered Compose must define exactly one network named cell")
    cell_network = networks["cell"]
    if not isinstance(cell_network, dict) or cell_network.get("internal") is not True:
        raise GuardDenied("Compose network cell must be internal")
    if cell_network.get("external") not in {None, False}:
        raise GuardDenied("Compose network cell must not be external")

    for service_name in SERVICES:
        service = services[service_name]
        if not isinstance(service, dict):
            raise GuardDenied(f"service {service_name} must be an object")
        if service.get("ports") not in (None, []):
            raise GuardDenied(f"service {service_name} publishes a host port")
        if service.get("expose") not in (None, []):
            raise GuardDenied(f"service {service_name} declares an exposed port")
        if _service_network_names(service) != {"cell"}:
            raise GuardDenied(
                f"service {service_name} must attach only to network cell"
            )
        if "network_mode" in service:
            raise GuardDenied(f"service {service_name} declares network_mode")
        if service.get("privileged") not in (None, False):
            raise GuardDenied(f"service {service_name} must not be privileged")
        if "env_file" in service:
            raise GuardDenied(f"service {service_name} must not use env_file")
        for volume in service.get("volumes", []) or []:
            if "docker.sock" in str(volume).lower():
                raise GuardDenied(f"service {service_name} mounts the Docker socket")

    app = services["app"]
    app_environment = {
        key.upper(): value for key, value in _environment_map(app).items()
    }
    expected_app_environment = {
        "APP_ENV": "local",
        "SESSION_COOKIE_SECURE": "false",
        "ENABLE_INPROCESS_CRON": "false",
    }
    for key, expected in expected_app_environment.items():
        if app_environment.get(key, "").lower() != expected:
            raise GuardDenied(f"app effective configuration must set {key}={expected}")
    leaked_app_keys = sorted(set(app_environment) & APP_DATA_DENIED)
    if leaked_app_keys:
        raise GuardDenied(
            "app effective environment contains forbidden keys: "
            + ",".join(leaked_app_keys)
        )

    app_depends = app.get("depends_on", {})
    seed_depends = services["seed"].get("depends_on", {})
    if not isinstance(app_depends, dict) or not isinstance(seed_depends, dict):
        raise GuardDenied("app and seed must declare the migration gate")
    for service_name, depends in (("app", app_depends), ("seed", seed_depends)):
        gate = depends.get("migrate")
        if (
            not isinstance(gate, dict)
            or gate.get("condition") != "service_completed_successfully"
        ):
            raise GuardDenied(
                f"{service_name}.depends_on.migrate must require service_completed_successfully"
            )

    browser_depends = services["browser"].get("depends_on", {})
    if not isinstance(browser_depends, dict):
        raise GuardDenied("browser must declare its app and seed dependency chain")
    if browser_depends.get("app", {}).get("condition") != "service_healthy":
        raise GuardDenied("browser must wait for a healthy app")
    if (
        browser_depends.get("seed", {}).get("condition")
        != "service_completed_successfully"
    ):
        raise GuardDenied("browser must wait for successful synthetic seed")


def validate_browser_source(source: str) -> None:
    """Static defense against real Chrome/profile use and proxy broadening."""

    forbidden = (
        "launchPersistentContext",
        "channel: 'chrome'",
        'channel: "chrome"',
        "userDataDir",
        "storageState",
        "0.0.0.0",
    )
    present = [token for token in forbidden if token in source]
    if present:
        raise GuardDenied(
            "browser runner contains forbidden persistence/bind token(s): "
            + ",".join(present)
        )
    required = (
        "chromium.launch",
        "browser.newContext",
        "serviceWorkers: 'allow'",
        "127.0.0.1",
        "hostname: 'app'",
        "port: 8000",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise GuardDenied(
            "browser runner is missing isolation token(s): " + ",".join(missing)
        )


def assert_zero_residuals(residuals: Mapping[str, int]) -> None:
    """Prevent a successful verdict while any exact manifest resource remains."""

    if any(not isinstance(value, int) or value != 0 for value in residuals.values()):
        raise AssertionFailure("recorded Docker resources remain after cleanup")


def assert_migration_gate(migration_exit_code: int | None, target_service: str) -> None:
    """Forbid seed/app/browser creation until the migrator has exited zero."""

    if target_service in {"seed", "app", "browser"} and migration_exit_code != 0:
        raise AssertionFailure(
            f"service {target_service} creation denied before successful migration"
        )


def timeout_status_for_phase(phase_name: str | None) -> str:
    """Map a bounded phase timeout to the receipt taxonomy."""

    if phase_name == "cleanup":
        return "CLEANUP_TIMEOUT"
    return "TEST_TIMEOUT" if phase_name == "browser" else "SETUP_TIMEOUT"


def assert_no_runtime_port_bindings(
    host_bindings: Any,
    runtime_ports: Any,
    *,
    service: str,
) -> None:
    """Accept image EXPOSE metadata only when every runtime binding is null."""

    normalized_bindings = host_bindings or {}
    if not isinstance(normalized_bindings, dict):
        raise AssertionFailure(f"service {service} runtime port bindings are invalid")
    published = sum(len(value or []) for value in normalized_bindings.values())
    if published != 0:
        raise AssertionFailure(f"service {service} published a host port")
    if runtime_ports not in (None, {}) and (
        not isinstance(runtime_ports, dict)
        or any(value not in (None, []) for value in runtime_ports.values())
    ):
        raise AssertionFailure(f"service {service} has a non-null runtime port binding")


def redact_text(value: str, *, replacements: Mapping[str, str] | None = None) -> str:
    """Redact owned absolute paths and known credential-shaped strings."""

    result = value
    for original, replacement in (replacements or {}).items():
        result = result.replace(original, replacement)
    result = re.sub(r"(?i)postgres(?:ql)?://[^\s'\"]+", "<redacted-db-url>", result)
    result = re.sub(
        r"(?i)https?://[^\s'\"]*(?:neon\.tech|fly\.dev)[^\s'\"]*",
        "<redacted-target>",
        result,
    )
    result = re.sub(
        r"[A-Za-z0-9._%+-]+@(?!example\.invalid\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "<redacted-email>",
        result,
    )
    return result
