"""Tests for reproducible, secret-safe Neon bootstrap preparation."""

from sqlalchemy.engine import URL, make_url

from scripts import bootstrap_neon


def test_placeholder_role_urls_are_replaced_from_owner_coordinates(monkeypatch, tmp_path) -> None:
    """Copying .env.example cannot preserve unusable app or migrator placeholders."""
    env_path = tmp_path / ".env"
    owner_url = URL.create(
        "postgresql",
        username="neondb_owner",
        password="test-owner-password",
        host="ep-test.example.invalid",
        database="neondb",
        query={"sslmode": "require"},
    ).render_as_string(hide_password=False)
    env_path.write_text(
        "\n".join(
            (
                f"NEON_OWNER_URL={owner_url}",
                "DATABASE_URL=postgresql://microsched_app:password@host/database",
                "NEON_MIGRATOR_URL=postgresql://microsched_migrator:password@host/database",
                "UNRELATED_SETTING=preserved",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bootstrap_neon, "ENV_PATH", env_path)

    values = bootstrap_neon.ensure_role_urls(provision=True)

    app_url = make_url(values["DATABASE_URL"])
    migrator_url = make_url(values["NEON_MIGRATOR_URL"])
    assert app_url.username == "microsched_app"
    assert migrator_url.username == "microsched_migrator"
    assert app_url.host == migrator_url.host == "ep-test.example.invalid"
    assert app_url.database == migrator_url.database == "neondb"
    assert app_url.password != "password"
    assert migrator_url.password != "password"
    assert "UNRELATED_SETTING=preserved" in env_path.read_text(encoding="utf-8")
