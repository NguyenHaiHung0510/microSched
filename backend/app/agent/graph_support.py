"""Small public contracts for restoring a LangGraph run from Mimi's durable ledger.

The graph saver is a control cursor only. Application code supplies a frame rebuilt
from its encrypted events and provider/tool journals; those payloads never belong in
LangGraph checkpoint state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.loop import LoopResult
from app.agent.openrouter import AgentCompletion


@dataclass(frozen=True)
class RestoredFrame:
    """Content frame independently reconstructed and verified by the app journal.

    For a saved ``read`` phase, ``messages`` ends immediately before the pending
    read result(s); those payloads and their request fingerprints live in the
    encrypted app journal and are supplied separately so the runner can append
    each result exactly once. ``pending_completion`` is a provider terminal whose
    dispatch is proven by that journal. For a saved ``model`` phase with no
    pending completion, ``dispatch_not_started`` must be true only when the app
    journal proves no provider dispatch began. Otherwise the callback should
    raise ``ProviderDispatchError(outcome="unknown")``.
    """

    messages: tuple[dict[str, Any], ...]
    seen_calls: frozenset[str] = frozenset()
    last_completion: AgentCompletion | None = None
    pending_completion: AgentCompletion | None = None
    dispatch_not_started: bool = False
    read_results: dict[str, Any] = field(default_factory=dict)
    read_result_fingerprints: dict[str, str] = field(default_factory=dict)
    terminal_result: LoopResult | None = None
