# Mimi context research — 2026-09-22

Status: **EVIDENCE COLLECTED — OWNER WORKSHOP PENDING — EVAL NOT AUTHORIZED**

This folder is the canonical evidence workspace for research into Mimi's system policy,
context assembly, tool/harness behavior, and context-control UX.

## Authority and stop conditions

- Owner approved research and use of T3 researchers on 2026-09-22.
- Runtime code, prompt deployment, paid/live eval, model adoption, and dogfood execution are
  not authorized by creation of this folder.
- `MIMI_DEMO_1` is the approved key alias for a later Owner-approved eval/live dogfood run.
  Never record or print its value.
- Every finding must distinguish `FACT`, `INFERENCE`, `PROPOSAL`, and `OPEN`.
- T1 presents research results and conducts an Owner requirements workshop before recommending
  the final Mimi design. T1 does not choose the product behavior alone.

## Product hypothesis to research, not assume

Mimi may need an iterative agent loop rather than a single terminal call:

- ordinary conversation and read-only questions may answer directly;
- bounded read tools may be used repeatedly to understand current microSched state;
- a **draft** is conversational analysis/options and is not executable;
- a **preview** is a frozen typed change set that can be confirmed and executed;
- explicit small and clear action requests may proceed directly to preview;
- broad, ambiguous, multi-record, or explicitly requested planning work may produce a draft
  before any executable preview;
- every write still requires the approved preview/confirmation boundary.

Exact thresholds and policies remain open until research and Owner review.

## Batch files

| Batch | File | Writer | State |
|---|---|---|---|
| B00 | `01-current-request-anatomy.md` | T3 Luna | COLLECTED |
| B01 | `02-spec-package-authority-map.md` | T3 Luna | COLLECTED |
| B02 | `03-cross-provider-prompt-research.md` | T3 Luna | COLLECTED |
| B03 | `04-agent-loop-and-interaction-policy.md` | T3 Gemini 3.8 Flash | RAW PROPOSAL; SEE B11 |
| B04 | `05-context-builder-and-manifest.md` | T3 Luna | COLLECTED |
| B05 | `06-tools-and-deterministic-gates.md` | T3 Luna | COLLECTED |
| B06 | `07-security-and-prompt-injection.md` | T3 Luna | COLLECTED |
| B07 | `08-provider-portability-cache-economics.md` | T3 Luna | COLLECTED |
| B08 | `09-ui-ux-context-controls.md` | T3 Gemini 3.8 Flash | RAW PROPOSAL; SEE B11 |
| B09 | `10-eval-design-draft.md` | T3 Gemini 3.8 Flash | DRAFT ONLY; SEE B11 |
| B10 | `11-owner-workshop-and-t1-synthesis.md` | T1 | D1–D4 APPROVED; D5–D7 READY FOR OWNER |
| B11 | `12-independent-evidence-critique.md` | T3 Luna | COLLECTED |
| B12 | `13-tool-granularity-and-bulk-operations.md` | T3 Luna | COLLECTED |
| B13 | `14-current-tool-surface-and-bulk-gap.md` | T3 Luna | COLLECTED |
| B14 | `15-loop-engine-and-harness.md` | T3 Luna | COLLECTED |

## Required report shape

Each batch file must include:

1. question and scope;
2. method and exact sources;
3. observed facts;
4. competing interpretations;
5. trade-offs;
6. recommendations, clearly marked as proposals;
7. unresolved questions for Owner/T1;
8. evidence version/date and limitations.

No agent may mark a research proposal as Owner-approved.

The independent critique in B11 controls how unsupported claims in raw proposal
files are used: T1 must not promote a disputed number, model capability, budget,
threshold, or UI assertion into the synthesis without fresh evidence or an Owner
decision.
