# Workspace context, preview and run diagnostics

Current source at the [indexed baseline](README.md): `frontend/src/MimiContextRail.tsx:50` and `:109`, `frontend/src/MimiContextComposition.tsx:24`. Runtime **NOT_RUN**.

## Sub-features

Workspace statistics and diagnostic disclosures, domain context, pending preview summary and run/context composition.

## How to get to it (user POV)

Open **Thống kê hội thoại** in Workspace. In `mimi-context-rail` expand **Dữ liệu và chẩn đoán**, then choose buttons **Context**, **Preview** or **Run**. The composer also exposes a separate context composition panel.

## Driving it in a current synthetic candidate

The disclosure buttons use `aria-expanded`. **Context** shows domain previews and **Mở đầy đủ** links. **Preview** shows pending composition and expiry; use the transcript to review or decide. **Run** provides `mimi-context-inspector` under **Route, nguồn context và mức dùng** and `mimi-run-observations`. The composer panel uses `mimi-run-context-inspector`.

Oracle: Domain previews, pending scope and actual run lineage agree with the same fixture. For byte and token assertions use attributable manifest and call receipts under the [context contract](../../../../docs/mimi/context.md). Serialized bytes, planning reserve, reported token/cache usage and missing values stay distinct.

## Gotchas

A current app-domain preview does not prove which records were sent to the model. Local static source has no attributable runtime usage.
