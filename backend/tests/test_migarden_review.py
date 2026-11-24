"""Terra F1 boundary regressions; no real target connection or credential."""

from types import SimpleNamespace

import pytest
from sqlalchemy.engine import make_url

from scripts import provision_migarden_qa as provision

LOCAL = "postgresql+asyncpg://synthetic:fixture@127.0.0.1:21891/microsched_n01_unit"


@pytest.mark.parametrize("drift", ["settings", "factory"])
def test_qa_provision_refuses_effective_redirect_before_any_connection(monkeypatch, drift):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", LOCAL)
    bad = LOCAL.replace("microsched_n01_unit", "another_database")
    settings = SimpleNamespace(
        is_production=False, database_url=bad if drift == "settings" else LOCAL
    )
    monkeypatch.setattr(provision, "Settings", lambda **kw: settings)
    calls = []
    engine = SimpleNamespace(url=make_url(bad if drift == "factory" else LOCAL))
    factory = SimpleNamespace(kw={"bind": engine})
    monkeypatch.setattr(
        provision, "get_sessionmaker", lambda target: (calls.append("factory"), factory)[1]
    )
    with pytest.raises(ValueError, match="resolved"):
        provision.checked_factory()
    assert calls == ([] if drift == "settings" else ["factory"])


@pytest.mark.parametrize(
    "url",
    [
        LOCAL.replace("127.0.0.1", "remote.example.invalid"),
        LOCAL.replace("microsched_n01_unit", "real_database"),
        LOCAL + "?host=remote.example.invalid",
    ],
)
def test_qa_provision_bad_target_never_resolves_settings_or_factory(monkeypatch, url):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", url)

    def forbidden():
        pytest.fail("settings or factory was resolved before refusing the explicit target")

    monkeypatch.setattr(provision, "Settings", forbidden)
    monkeypatch.setattr(provision, "get_sessionmaker", forbidden)
    with pytest.raises(ValueError, match="explicit local"):
        provision.checked_factory()


def test_qa_provision_matches_resolved_factory_exactly(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", LOCAL)
    settings = SimpleNamespace(is_production=False, database_url=LOCAL)
    factory = SimpleNamespace(kw={"bind": SimpleNamespace(url=make_url(LOCAL))})
    monkeypatch.setattr(provision, "Settings", lambda **kw: settings)
    monkeypatch.setattr(provision, "get_sessionmaker", lambda target: factory)
    assert provision.checked_factory() is factory
