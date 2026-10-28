"""Explicit one-time LangGraph saver setup for a local synthetic P1C database."""

from __future__ import annotations

import asyncio
import os
import selectors

from sqlalchemy.engine import make_url


def _local_owner_url() -> str:
    value = os.environ.get("MIMI_LANGGRAPH_QA_DATABASE_URL")
    if not value:
        raise SystemExit("MIMI_LANGGRAPH_QA_DATABASE_URL is required")
    url = make_url(value)
    if (
        url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.port is None
        or not (url.database or "").startswith("microsched_p1ca")
        or url.username != "postgres"
    ):
        raise SystemExit("refusing saver setup outside local microsched_p1ca* owner database")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


async def _setup(conn_string: str) -> None:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg import AsyncConnection

    async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
        await saver.setup()
    # The stock saver owns these three tables in public. Grant only the DML it
    # needs to the existing app role; never grant schema/database ownership.
    async with await AsyncConnection.connect(conn_string, autocommit=True) as connection:
        await connection.execute("GRANT USAGE ON SCHEMA public TO microsched_app")
        await connection.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            "public.checkpoints, public.checkpoint_blobs, public.checkpoint_writes "
            "TO microsched_app"
        )
        await connection.execute(
            "GRANT SELECT ON TABLE public.checkpoint_migrations TO microsched_app"
        )


def main() -> None:
    conn_string = _local_owner_url()
    asyncio.run(
        _setup(conn_string),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
    print("Saver tables prepared; narrowly scoped DML granted to microsched_app.")


if __name__ == "__main__":
    main()
