"""Every actual assistant producer must declare its source and await the pair."""

import ast
from collections import Counter
from pathlib import Path

from app.agent.message_provenance import PRODUCERS


def test_all_assistant_message_producers_are_explicit_and_awaited():
    root = Path(__file__).parents[1] / "app"
    codes = []
    callsites = Counter()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name != "_add_assistant_message":
                continue
            assert isinstance(parents[node], ast.Await), f"{path}:{node.lineno} not awaited"
            metadata = {k.arg: k.value for k in node.keywords}
            code = ast.literal_eval(metadata["producer_code"])
            assert code in PRODUCERS
            assert ("provider_call_id" in metadata) == (PRODUCERS[code] == "model_answer")
            codes.append(code)
            owner = node
            while not isinstance(owner, (ast.AsyncFunctionDef, ast.FunctionDef, ast.Module)):
                owner = parents[owner]
            callsites[(path.relative_to(root).as_posix(), getattr(owner, "name", None), code)] += 1
    # The shared typed-Undo terminal is a second deliberate use of the local
    # deterministic producer. Bind every code to its owning function and file;
    # a total count alone would miss moved or duplicated ownership.
    expected = Counter(
        {
            ("agent/service.py", "send_message", code): 1
            for code in (
                "provider_text",
                "agent_loop_stop",
                "context_budget_stop",
                "checkpoint_unknown",
                "checkpoint_materialization_failed",
                "provider_output_rejected",
                "provider_terminal",
                "local_deterministic_result",
                "conversation_frontier_changed",
                "preview_frontier_changed",
                "pending_preview_requires_decision",
            )
        }
    )
    expected.update(
        {
            ("agent/service.py", "confirm_change_set", "operation_committed"): 1,
            ("agent/service.py", "_confirm_collection", "collection_committed"): 1,
            ("agent/service.py", "add_preview_notice", "undo_prepared"): 1,
            ("agent/service.py", "add_preview_notice", "preview_prepared"): 1,
            ("agent/service.py", "reconcile_orphaned_mimi_runs", "process_loss_recovery"): 1,
            ("agent/service.py", "_record_typed_undo_rejection", "local_deterministic_result"): 1,
            ("agent/voice_store.py", "transcript", "provider_voice"): 1,
            ("agent/voice_store.py", "transcript", "provider_voice_partial"): 1,
        }
    )
    assert set(codes) == set(PRODUCERS)
    assert callsites == expected
