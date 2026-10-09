"""Every actual assistant producer must declare its source and await the pair."""

import ast
from pathlib import Path

from app.agent.message_provenance import PRODUCERS


def test_all_assistant_message_producers_are_explicit_and_awaited():
    root = Path(__file__).parents[1] / "app"
    codes = []
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
    assert set(codes) == set(PRODUCERS) and len(codes) == 15
