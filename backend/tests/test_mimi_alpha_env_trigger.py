"""Alpha preset must boot from declared .env and reject unsupported values."""

import pytest
from pydantic import ValidationError

from app.core.settings import Settings


@pytest.mark.parametrize("trigger", [100000, 272000])
def test_approved_compaction_trigger_parses_from_environment(monkeypatch, trigger):
    monkeypatch.setenv("MIMI_COMPACTION_TRIGGER_TOKENS", str(trigger))
    settings = Settings(_env_file=None, app_env="local")
    assert settings.mimi_compaction_trigger_tokens == trigger


@pytest.mark.parametrize("value", ["32000", "131072", "garbage"])
def test_unsupported_compaction_trigger_is_rejected(monkeypatch, value):
    monkeypatch.setenv("MIMI_COMPACTION_TRIGGER_TOKENS", value)
    with pytest.raises(ValidationError, match="mimi_compaction_trigger_tokens"):
        Settings(_env_file=None, app_env="local")
