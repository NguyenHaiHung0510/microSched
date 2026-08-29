"""Static guardrails for production Fly configuration that must survive deploys."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_fly_config_keeps_512mb_swap() -> None:
    """A regenerated fly.toml must not silently remove the OOM spike buffer."""
    config = tomllib.loads((REPO_ROOT / "fly.toml").read_text(encoding="utf-8"))
    swap_size_mb = config.get("swap_size_mb")

    assert type(swap_size_mb) is int
    assert swap_size_mb == 512
    assert all("swap_size_mb" not in vm for vm in config.get("vm", []))
