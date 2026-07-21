"""Helpers for safe Postgres URL normalization without logging credentials."""

from sqlalchemy.engine import URL, make_url


def async_postgres_url(value: str) -> str:
    """Return an asyncpg SQLAlchemy URL and drop unsupported provider options."""
    url = make_url(value)
    query = dict(url.query)
    query.pop("channel_binding", None)
    sslmode = query.pop("sslmode", None)
    if sslmode is not None:
        query["ssl"] = sslmode
    return url.set(drivername="postgresql+asyncpg", query=query).render_as_string(
        hide_password=False
    )


def asyncpg_dsn(value: str) -> str:
    """Return a direct asyncpg DSN while preserving TLS-related query options."""
    url = make_url(value)
    query = dict(url.query)
    query.pop("channel_binding", None)
    return url.set(drivername="postgresql", query=query).render_as_string(hide_password=False)


def role_url(owner_value: str, username: str, password: str) -> str:
    """Build a sibling role URL on the same Neon database as the owner URL."""
    owner = make_url(owner_value)
    return URL.create(
        "postgresql",
        username=username,
        password=password,
        host=owner.host,
        port=owner.port,
        database=owner.database,
        query=dict(owner.query),
    ).render_as_string(hide_password=False)
