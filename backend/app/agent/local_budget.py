"""Finite local synthetic paid-call ledger, independent of model prose.

Opt-in private file supplied by T1, cumulative baseline includes older unknown
holds. This is deliberately a local QA grant, not production billing policy.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

import httpx

from app.agent.openrouter import RouteContractError, serialized_input_bytes
from app.core.settings import Settings


@contextmanager
def _locked(path: Path):
    lock = path.with_suffix(".lock")
    with lock.open("a+b") as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _path(settings: Settings) -> Path | None:
    name = os.environ.get("MIMI_LOCAL_BUDGET_LEDGER")
    if not name:
        return None
    if settings.app_env != "local":
        raise RouteContractError("local_budget_requires_local_environment")
    return Path(name)


def _write(path: Path, ledger: dict) -> None:
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    temporary.replace(path)


def key_meter(settings):
    # Secure runtime mapping of MIMI_DEMO_1 supplied by the authorized dotenv
    # loader; never print headers/value or pass it in command arguments.
    if not settings.mimi_standard_api_key:
        raise RouteContractError("local_budget_authorized_key_missing")
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            response = client.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": "Bearer " + settings.mimi_standard_api_key},
            )
        if response.status_code != 200:
            raise RouteContractError("local_budget_key_meter_unavailable")
        data = response.json()["data"]
        usage = Decimal(str(data["usage"]))
        remaining = Decimal(str(data["limit_remaining"]))
        if not usage.is_finite() or not remaining.is_finite() or usage < 0 or remaining < 0:
            raise ValueError("meter_invalid")
        return usage, remaining
    except httpx.HTTPError, KeyError, TypeError, ValueError, InvalidOperation:
        raise RouteContractError("local_budget_key_meter_unknown") from None


def reserve(
    settings: Settings, messages: list[dict], *, agent_contract: bool, summary_mode: bool = False
) -> str | None:
    path = _path(settings)
    if path is None:
        return None
    # Bytes are conservative token upper bound, including tools/schema.
    upper_input = serialized_input_bytes(
        messages, agent_contract=agent_contract, summary_mode=summary_mode
    )
    if settings.mimi_route_max_input_price is None or settings.mimi_route_max_output_price is None:
        raise RouteContractError("local_budget_route_price_missing")
    maximum = (
        Decimal(upper_input) * Decimal(str(settings.mimi_route_max_input_price))
        + Decimal(settings.mimi_route_max_output_tokens)
        * Decimal(str(settings.mimi_route_max_output_price))
    ) / Decimal(1_000_000)
    with _locked(path):
        ledger = json.loads(path.read_text(encoding="utf-8"))
        if ledger.get("grant_key_name") != "MIMI_DEMO_1" or Decimal(ledger["cap_usd"]) > 1:
            raise RouteContractError("local_budget_grant_invalid")
        if datetime.now(UTC) >= datetime.fromisoformat(ledger["expires_at_utc"]):
            raise RouteContractError("local_budget_grant_expired")
        if any(c["state"] != "accounted" for c in ledger["calls"]):
            raise RouteContractError("local_budget_prior_spend_unknown")
        max_calls = ledger.get("max_paid_dispatches", 16)
        if (
            not isinstance(max_calls, int)
            or isinstance(max_calls, bool)
            or not 1 <= max_calls <= 16
        ):
            raise RouteContractError("local_budget_dispatch_grant_invalid")
        if len(ledger["calls"]) >= max_calls:
            raise RouteContractError("local_budget_dispatch_cap_exhausted")
        total = Decimal(ledger["historical_accounted_usd"]) + sum(
            (Decimal(c["charged_or_reserved_usd"]) for c in ledger["calls"]), Decimal(0)
        )
        usage, remaining = key_meter(settings)
        baseline = ledger.get("baseline_key_usage")
        if baseline is None:
            raise RouteContractError("local_budget_key_meter_baseline_missing")
        measured = usage - Decimal(str(baseline))
        if measured < 0:
            raise RouteContractError("local_budget_key_meter_lineage_invalid")
        ledger["last_key_meter"] = {
            "usage": str(usage),
            "remaining": str(remaining),
            "observed_at": datetime.now(UTC).isoformat(),
        }
        _write(path, ledger)
        if measured + maximum > Decimal(ledger["cap_usd"]) or remaining < maximum:
            raise RouteContractError("local_budget_key_meter_exhausted")
        if total + maximum > Decimal(ledger["cap_usd"]):
            raise RouteContractError("local_budget_exhausted")
        call_id = str(uuid4())
        ledger["calls"].append(
            {
                "id": call_id,
                "state": "reserved_unknown",
                "model": settings.mimi_route_model,
                "provider": settings.mimi_route_provider,
                "effort": settings.mimi_route_reasoning_effort,
                "input_upper_bound": upper_input,
                "output_cap": settings.mimi_route_max_output_tokens,
                "reservation_usd": str(maximum),
                "charged_or_reserved_usd": str(maximum),
                "reserved_at": datetime.now(UTC).isoformat(),
            }
        )
        _write(path, ledger)
    return call_id


def account(settings: Settings, call_id: str | None, usage: dict, response_id: str | None) -> None:
    path = _path(settings)
    if path is None or call_id is None:
        return
    with _locked(path):
        ledger = json.loads(path.read_text(encoding="utf-8"))
        call = next(c for c in ledger["calls"] if c["id"] == call_id)
        call["response_id"] = response_id
        call["usage"] = usage
        cost = usage.get("cost")
        # Missing authoritative cost keeps the full hold, never guesses zero.
        if isinstance(cost, (int, float, str)) and not isinstance(cost, bool):
            charged = Decimal(str(cost))
            if not charged.is_finite() or charged < 0:
                raise RouteContractError("local_budget_usage_cost_invalid")
            call["state"] = "accounted"
            call["charged_or_reserved_usd"] = str(charged)
        call["observed_at"] = datetime.now(UTC).isoformat()
        _write(path, ledger)
        if call["state"] != "accounted":
            raise RouteContractError("local_budget_current_spend_unknown")
        if sum(
            (Decimal(c["charged_or_reserved_usd"]) for c in ledger["calls"]),
            Decimal(ledger["historical_accounted_usd"]),
        ) > Decimal(ledger["cap_usd"]):
            raise RouteContractError("local_budget_provider_cost_exceeded_reservation")
