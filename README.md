# microSched

English | [Tiếng Việt](README.vi.md)

[![CI](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml?query=branch%3Adevelop)
[![CodeQL](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/codeql.yml/badge.svg?branch=develop)](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/codeql.yml?query=branch%3Adevelop)
[![Latest release](https://img.shields.io/github/v/release/NguyenHaiHung0510/microSched?display_name=tag)](https://github.com/NguyenHaiHung0510/microSched/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Visit the website](https://microsched.fly.dev/home?lang=en)

**microSched** is my all-in-one personal app and personal software laboratory—the third and most mature version so far in my journey of building personal tools.

That journey started with [Code_HoTro_HocTap](https://github.com/NguyenHaiHung0510/Code_HoTro_HocTap) (a basic C++ CLI from my first year at university), continued with [VC_QuanLyThoiGian](https://github.com/NguyenHaiHung0510/VC_QuanLyThoiGian) (a vibe-coded Python/Flet desktop app packaged as an `.exe`), and led to microSched (harness engineering + AI engineering). It reflects how my product thinking, engineering, and collaboration with AI have matured. I have been using microSched in real life since **21 July 2026** and continue to improve it based on real-world feedback.

> This is a personal project under active development. This document describes what is currently in the code; not every idea on the roadmap has shipped.

## Current features

- **Tasks:** deadlines, checklists, priorities, pinning, overdue status, rescheduling, and recovery after soft deletion.
- **Notes:** Markdown content, checklists, time information, pinning/priorities, and private visibility.
- **Calendar:** ICS calendar sources, manually created sessions, a day-by-day scrolling calendar, annotations, and task rescheduling.
- **Tracking:** quick capture for health or finance trackers, timestamped entries, a VND dashboard, and recurring subscriptions/renewals.
- **Privacy:** Google OAuth with an allowlist, server-side sessions, and a separate private unlock for the display layer. Encryption at rest has its own boundaries; this is not a claim of security certification.
- **PWA:** install and use on a laptop or iPhone, with a service worker and Web Push foundations. A full offline outbox for all writes has not shipped.

## Learning goals and ecosystem

microSched is my **central project**, where I practice product thinking, backend/API development, data modeling, privacy boundaries, evaluation, and production operations. Related efforts under development or exploration—**not claimed as shipped**—include:

- **Mimi:** an AI agent for plan management, integrated with the website.
- **microLink:** a local MCP bridge between an AI agent and microSched.
- **miGarden:** an IoT system for plant monitoring and watering assistance, planned to integrate with microSched through a natural integration point.
- Other related products may follow when there is a clear need and scope.
- A read-only AI assistant, hybrid retrieval, write tools with confirmation/audit, and a full offline outbox remain on the roadmap or in progress; the MCP protocol is not enabled in microSched today.

## Architecture

```text
React + TypeScript PWA (browser: laptop / iPhone)
                 │ JSON API, same origin
                 ▼
FastAPI modular monolith (one Python process)
                 │
                 ▼
Neon PostgreSQL + pgvector
```

The frontend is a static SPA/PWA installed and used on a laptop or iPhone; the app already has a service worker and Web Push foundations. Node is used only at build time, while production runs one Python process serving both the API and the frontend build. Domain, web, retrieval, agent, and jobs stay in the same process; there are no microservices or Redis broker.

## Production infrastructure

- **Application:** FastAPI modular monolith + static React/TypeScript PWA.
- **Data:** Neon PostgreSQL with `pgvector`; private fields use the app's encryption boundary.
- **Actual delivery:** GitHub Actions builds and checks → Docker multi-stage build → one Fly.io Machine in `sin`, with a shared CPU, 256 MB RAM, and 512 MB swap; data lives in Neon PostgreSQL + `pgvector`. I use the app in real life on a laptop and iPhone.
- **Auth:** Google OAuth allowlist and server-side sessions.

## Running locally

### Backend

Requires Python 3.14 and `uv`. From the repository directory:

```powershell
cd backend
uv sync
Copy-Item .env.example .env
uv run uvicorn app.main:create_app --factory --reload
```

Fill in the local variables in `backend/.env` following `backend/README.md`. Do not use an owner/migrator URL as the runtime URL; do not commit `.env` or real secrets.

### Frontend

Requires Node 24 and npm:

```powershell
cd frontend
npm ci
npm run dev
```

Vite serves the development frontend; the backend runs separately at `http://localhost:8000`. Production does not run a second Node process.

## Quality checks

```powershell
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest

cd ..\frontend
npm run lint
npm test
npm run build
```

CI also includes Frontend e2e, secret scanning, and Migration QA with Postgres/pgvector. The commands above show how to run the checks; consult the corresponding CI receipts for the current pass status.

## Security and contributing

- See [SECURITY.md](SECURITY.md) to report vulnerabilities through GitHub private vulnerability reporting.
- See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a change.
- Do not include credentials, real personal data, OAuth allowlists, or production payloads in issues, PRs, logs, or fixtures.

## License

Source code and project-owned logos/icons are released under the [MIT License](LICENSE). Dependencies and third-party assets retain their respective licenses; personal data, secrets, credentials, and service accounts are not covered by the project's license.
