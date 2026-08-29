"""Helpers for safe Postgres URL normalization without logging credentials."""

from sqlalchemy.engine import URL, make_url


class SchedulerLockUrlError(ValueError):
    """Raised when a pooled URL cannot prove a direct lock connection."""


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


def scheduler_lock_dsn(value: str) -> str:
    """Build the dedicated scheduler-lock DSN without changing application DB use.

    A session-level advisory lock has to stay on one physical Postgres
    connection.  Neon pooler hostnames have a one-to-one direct spelling, so
    only that documented topology is rewritten.  Other apparent poolers fail
    closed instead of silently attaching the ownership fence to a connection
    that a pooler may later reuse.
    """
    url = make_url(value)
    host = (url.host or "").rstrip(".").lower()
    labels = host.split(".")
    endpoint = labels[0] if labels else ""

    if endpoint.endswith("-pooler"):
        if not host.endswith(".neon.tech") or len(endpoint) == len("-pooler"):
            raise SchedulerLockUrlError("scheduler ownership requires a supported direct endpoint")
        direct_host = f"{endpoint.removesuffix('-pooler')}.{'.'.join(labels[1:])}"
        url = url.set(host=direct_host)
    elif "pooler" in host:
        raise SchedulerLockUrlError("scheduler ownership requires a supported direct endpoint")

    return asyncpg_dsn(url.render_as_string(hide_password=False))


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
