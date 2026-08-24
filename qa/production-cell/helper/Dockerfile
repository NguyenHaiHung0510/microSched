FROM python:3.14-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /helper
RUN uv pip install --system --no-cache asyncpg==0.31.0

COPY qa/production-cell/helper/ /helper/

ENTRYPOINT ["python", "/helper/cell_helper.py"]
