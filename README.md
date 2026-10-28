# microSched

English | [Tiếng Việt](README.vi.md)

[![CI](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/NguyenHaiHung0510/microSched)](https://github.com/NguyenHaiHung0510/microSched/releases/latest)

[Visit microSched](https://microsched.fly.dev/home?lang=en) · [Technical documentation](docs/project-guide.md) · [Changelog](CHANGELOG.md)

microSched is a personal task, note, calendar and tracking PWA for one Owner. It is also a software laboratory for harness engineering and AI engineering, following [Code_HoTro_HocTap](https://github.com/NguyenHaiHung0510/Code_HoTro_HocTap) and [VC_QuanLyThoiGian](https://github.com/NguyenHaiHung0510/VC_QuanLyThoiGian).

- **Tasks and notes:** deadlines, priorities, pinning, checklists, soft-delete/recovery and Markdown reading/editing.
- **Calendar and reminders:** ICS sources, manual events, date/time movement, day annotations, one-shot and recurring reminders, delivery/history views.
- **Tracking:** grouped trackers, timestamped entries, funding/income capture, VND reports and subscription renewals.
- **Responsive PWA:** shared navigation, compact content, offline public bootstrap and a durable outbox for **11 Task/checklist/Entry commands**. Other domains still need a connection; pending local admission and server confirmation are distinct states.
- **Privacy:** Google OAuth allowlist, opaque server-side sessions, private display unlock and application encryption boundaries.
- **Mimi:** Task/checklist reading, proposals, review/revision and explicit confirmation are delivered. Mimi as a whole remains in development; see its [PARTIAL technical README](docs/mimi/README.md).

React/TypeScript/Vite builds a static frontend. One FastAPI process serves the SPA and API, with PostgreSQL/pgvector on Neon. Node is needed for development/build only. The checked-in Fly configuration uses one always-on machine; current runtime health requires separate evidence.

For a fresh checkout, start with [development setup](docs/engineering/development.md). It covers Python 3.14, Node 24, `uv sync --frozen`, `npm ci`, environment roles and tests. [Operations](docs/operations/runbook.md) covers deployment, readiness, backup/recovery and separately authorized migrations. The documentation describes current source; it does not certify every browser, physical device or live-provider journey.

See [contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md). Keep credentials, account identifiers and personal data out of issues, fixtures and PRs. Source and project-owned logos/icons use the [MIT License](LICENSE); third-party assets retain their own licenses. Personal data and service accounts are excluded.
