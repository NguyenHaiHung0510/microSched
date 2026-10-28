# microSched

English | [Tiếng Việt](README.vi.md)

[![CI](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/NguyenHaiHung0510/microSched)](https://github.com/NguyenHaiHung0510/microSched/releases/latest)

[Visit microSched](https://microsched.fly.dev/home?lang=en) · [Technical documentation](docs/project-guide.md) · [Changelog](CHANGELOG.md)

**microSched** is my all-in-one personal app and personal software laboratory—the third and most mature version so far in my journey of building personal tools.

That journey started in my first year at university with [Code_HoTro_HocTap](https://github.com/NguyenHaiHung0510/Code_HoTro_HocTap), a C++ command-line study journal for recording daily learning, keeping notes by subject or task, and rating my progress. It continued with [VC_QuanLyThoiGian](https://github.com/NguyenHaiHung0510/VC_QuanLyThoiGian), a vibe-coded Python/Flet desktop app for managing personal tasks and schedules, packaged as a Windows `.exe`. Today, microSched brings tasks, notes, calendars and trackers into a personal web app, with Mimi adding AI assistance for Task/checklist work.

These are three generations of personal tools and three stages in my learning: practicing programming through a small CLI, building a desktop app with AI, and developing and operating a broader product with a coordinated team of agents. Each stage reflects growth in my product thinking, engineering and collaboration with AI. I have been using microSched in real life since **21 August 2026** and continue to improve it based on real-world feedback.

## What I use it for

microSched brings my tasks, notes, calendar and trackers together in a PWA built for my own daily use.

- **Tasks and notes:** deadlines, priorities, pinning, checklists, soft-delete/recovery and Markdown reading/editing.
- **Calendar and reminders:** ICS sources, manual events, date/time movement, day annotations, one-shot and recurring reminders, delivery/history views.
- **Tracking:** grouped trackers, timestamped entries, funding/income capture, VND reports and subscription renewals.
- **Responsive PWA:** shared navigation, compact content, offline public bootstrap and a durable outbox for **11 Task/checklist/Entry commands**. Other domains still need a connection; pending local admission and server confirmation are distinct states.
- **Privacy:** Google OAuth allowlist, opaque server-side sessions, private display unlock and application encryption boundaries.
- **Mimi:** Task/checklist reading, proposals, review/revision and explicit confirmation are delivered. Mimi as a whole remains in development; see its [PARTIAL technical README](docs/mimi/README.md).

## What I learn by building it

I am working toward becoming an **AI engineer**. microSched gives me a place to experiment and learn while building a product I actually use. Everyday needs help me choose what to build, and real use shows where a design, an implementation or an AI-assisted workflow needs to improve.

- **Harness engineering and agent orchestration:** organizing agents into roles, including a PM to manage scope, priorities and coordination; giving agents clear tasks and context; and reviewing their work (by delegating reviews to other agents too xD) before integrating it into the project. I am learning how to organize AI-assisted development as a working team.
- **Software engineering and operations:** working across the frontend, backend and database, then taking changes through deployment, CI/CD, verification, backups and maintenance. Keeping my own app useful makes reliability and maintainability practical concerns.
- **AI engineering with Mimi:** developing an AI module inside the app, from model and tool integration to context, Task/checklist proposals, explicit confirmation and recovery. Mimi lets me work on the behavior of an AI product and evaluate how well it helps with actual tasks.

Building, learning and using the app feed back into one another: I try an approach, check the result, use it in daily life and bring what I learn into the next change.

## Technical overview and getting started

React/TypeScript/Vite builds a static frontend. One FastAPI process serves the SPA and API, with PostgreSQL/pgvector on Neon. Node is needed for development/build only. The checked-in Fly configuration uses one always-on machine; current runtime health requires separate evidence.

For a fresh checkout, start with [development setup](docs/engineering/development.md). It covers Python 3.14, Node 24, `uv sync --frozen`, `npm ci`, environment roles and tests. [Operations](docs/operations/runbook.md) covers deployment, readiness, backup/recovery and separately authorized migrations. The documentation describes current source; it does not certify every browser, physical device or live-provider journey.

See [contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md). Keep credentials, account identifiers and personal data out of issues, fixtures and PRs. Source and project-owned logos/icons use the [MIT License](LICENSE); third-party assets retain their own licenses. Personal data and service accounts are excluded.
