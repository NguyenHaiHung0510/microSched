"""Static guardrails for production Fly configuration that must survive deploys."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_fly_config_keeps_512mb_swap() -> None:
    """A regenerated fly.toml must not silently remove the OOM spike buffer."""
    config = tomllib.loads((REPO_ROOT / "fly.toml").read_text(encoding="utf-8"))

    assert config.get("swap_size_mb") == 512
