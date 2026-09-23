# Mimi slide handoff — 2026-09-23

Audience: the parallel Codex task `(T1) Đánh giá lại kiến trúc Mimi (branched)` and Owner.
This is a progress handoff, **not** a replacement for that task's previously agreed slide outline.
The parallel agent should tell Owner what narrative/section structure it had already agreed with
them before adapting these facts. T1 in this task cannot inspect or message that separate Codex
task through the currently exposed thread tools; this file is the explicit handoff artifact.

## Progress facts safe to present

- Mimi P0 sandbox/contracts and P1 walking skeleton were implemented before the current P1C
  correction. The old local dogfood failed as a useful live-model demo; later UI dogfood improved
  side-chat, conversation management and workspace, but visual acceptance did not prove model
  quality or real Task execution. Use the original package receipts to state exact historical
  commit/merge/deploy claims.
- The current P1C-A branch is `feat/065-mimi-p1c-context-loop` in the dedicated worktree. Its
  objective is to replace Task-create-only inline prompting with a versioned Vietnamese system
  policy, provider-neutral context manifest, bounded iterative STANDARD Task reads, direct
  answer/clarification/strategic draft/frozen preview outcomes, confirmation seam, encrypted
  canonical checkpoint and truthful crash recovery. P1C-B bulk workflows are later.
- Offline/local evidence at the time of writing: backend non-Postgres 545 pass/1 skip; disposable
  PostgreSQL 232 pass after the new cases; frontend Vitest 160 pass; synthetic Playwright 272
  pass/34 skip after the replay/keyboard UI corrections, including targeted Mimi Playwright 6/6 pass.
  Independent review found a forgeable pagination cursor; it has since been HMAC-signed and a
  tamper test went RED with guard disabled and GREEN after restoration. A persisted encrypted
  checkpoint rehydration/tamper test also passes on disposable PostgreSQL. Further decision tests
  show exact preview revision CAS and stale-source confirmation failing safely. Two provenance
  gaps found by independent review were closed: aggregate-backed preview is blocked until it can
  be freshness-bound, and a Task changing between two reads halts the run. These are local
  deterministic receipts. A new isolated browser lane now also covers real local auth → FastAPI
  SSE → fake provider → disposable PostgreSQL at desktop/mobile (2 PASS), including draft,
  preview/receipt, identical side/workspace preview digest, a run that survives tab switch/reload,
  explicit reconcile/Resume, checkpoint display, 30-second deadline and Owner cancellation.
  Its fresh synthetic database began and ended with zero Task/change-set/receipt/provider-call
  rows after exact linked cleanup. This is deliberately **not** a live-model result. Frozen-commit
  independent review and CI are still pending at this timestamp.
- No external model evaluation or real API key use has happened in P1C-A. OpenRouter Stage 0,
  D10's 42-run GLM cohort, MIDEX-mini, Chrome MCP live acceptance, Owner live dogfood, PR/CI,
  merge and production deploy are **NOT RUN/NOT DONE** for this branch. Do not call P1C-A
  accepted, live, or production-ready.
- Next sequence: finish deterministic QA and independent review; freeze commit and PR/CI; present
  exact D10 route/token/cost/resource packet for Owner approval; only then run Stage 0 and D10.
  Chrome live QA and Owner dogfood are separate later gates. The Owner explicitly removed the
  pressure to have a new live dogfood demo ready for the morning presentation.

## Suggested honest slide message (not a new approved outline)

"Mimi đã đi từ hợp đồng an toàn và walking skeleton sang P1C-A: ngữ cảnh có phiên bản, đọc dữ
liệu có giới hạn, phân biệt hỏi/nháp/preview và giữ quyền xác nhận của người dùng. QA offline và
Postgres synthetic đang được đóng; đánh giá model live và dogfood của chủ vẫn là bước kế tiếp,
chưa được tuyên bố PASS."

Do not expose credentials, account identifiers, real Task data or local raw evaluation payloads
on slides. The owner-approved design identity is being handled by a parallel workstream; do not
improvise a new Mimi/Orbit logo for the presentation.
