FROM node:24-bookworm-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.14-slim-bookworm AS runtime

ARG GIT_SHA=unknown

ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    GIT_SHA=${GIT_SHA}

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist/

RUN groupadd --system microsched \
    && useradd --system --gid microsched --home-dir /app --no-create-home microsched \
    && chown -R microsched:microsched /app

USER microsched
WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
