# Verification và provenance

Chọn check theo delta/risk; required và committed gates vẫn bắt buộc. [Development](../engineering/development.md) giữ lệnh tái lập; [CI](../../.github/workflows/ci.yml) giữ runner hiện hành. Source mapping không phải runtime acceptance.

| Lớp | Chứng minh | Không tự chứng minh |
|---|---|---|
| Unit/contracts, mocks/SDK doubles | Logic, request shape, lifecycle, safety/accounting và deterministic oracle | Chất lượng model/provider thật |
| Build/static/PWA/brand | TypeScript, bundle/assets, SW/icon/surface contracts | Mọi thiết bị hoặc profile upgrade |
| Disposable PostgreSQL | SQL/grants, constraints, transactions/CAS, drift/round-trip | Schema/data live Neon |
| Synthetic full-app browser | Journey + API/DB đúng freeze, drafts/pending/reload và ảnh quan sát | Real OAuth, physical iPhone/Safari, live-model quality |
| Bounded live-model QA | Behavior, source/tool grounding, call/cost dưới grant riêng | Mọi prompt/provider hoặc toàn bộ Mimi |
| Production readiness | Exact deployed commit + db=up + config/deploy evidence | Mọi flow hoặc physical-device acceptance |

Tách OBSERVED/INFERRED/UNVERIFIED/NOT_RUN/PARTIAL/BLOCKED; attempted/run/worker PASS/T1 accepted và mẫu số. Giữ failure/recovery, measured calls/time/cost và unknown. Timeout không chứng minh không có effect.

## Maintained contracts và runners

- [UI QA](../qa-framework.md) giữ accessibility/taste/state/data/device checks và §2.1 Owner sync → authorized scrub. [Agent QA](../qa-agent-framework.md) giữ stream/recovery, confirmation, deterministic/live evidence, isolation và budgets.
- [Reading gates](reading-gates.md) là maintained registry và verification contract; domain diagnostic locator trỏ vào đây.
- [Production cell](../../qa/production-cell/run.py) là isolated Compose runner. [Receipt schema](../../qa/production-cell/contracts/qa-receipt.schema.json) là validator input, khác generated receipt JSON. Root command `python -m unittest discover -s qa/production-cell/tests -v` kiểm schema/cell/guards không start Docker. [requirements.lock](../../qa/production-cell/requirements.lock), manifests/envelopes và cleanup guards giữ nguyên.
- Mimi [case oracle](../qa-specs/mimi-task-collection-cases.json) và [selector manifest](../qa-specs/mimi-task-collection-execution.json) là executable test inputs. [Runner](../../backend/scripts/run_mimi_collection_case.py) dùng manifest; `--collect-only` kiểm loading/selectors không chạy PG/provider. `*-last-execution`, `*-affected-execution`, `*-app-execution` và binding erratum là dated execution/provenance records, không phải verdict hiện tại hoặc oracle thay thế. Giữ case IDs/denominators.
- [Collection QA](../qa-specs/qa-mimi-task-collection.md), [real conversation](../qa-specs/qa-mimi-078-real-conversation.md), [P1 dogfood](../qa-specs/qa-mimi-p1-live-dogfood.md) giữ gates đã cam kết. Historical expiry/budget/key/activation chỉ mô tả batch cũ, không cấp quyền gọi lại. Batch mới cần grant/freeze/capabilities hiện tại.
- [microSched skill](../../.agents/skills/verify-microsched/SKILL.md), [recipes](../../.agents/skills/verify-microsched/features/README.md); [Mimi skill](../../.agents/skills/verify-mimi/SKILL.md), [recipes](../../.agents/skills/verify-mimi/features/README.md) giữ source/runner navigation. Không sửa guard của historical driver để nhập checkout mới.

Freeze source/build/config/fixture/oracle/capabilities/resources tại đầu batch và material delta. Runtime owner kiểm exact identity/ports/images/volumes; giữ unrelated processes/profiles/tabs. Independent QA handback whole batch rồi T1 reconcile/group repairs/retest; builder smoke là evidence riêng.

## Evidence ngoài repository

Owner quản lý archive local riêng với INDEX.md, abstract/matrix, report+media links và backing receipts cần thiết. Public repo không phân phối private transcript/payload, backup/key hoặc đường dẫn máy riêng. Hỏi Owner/PM locator local; không suy mọi clone đều có archive đó.

| Historical group | Scoped conclusion và provenance |
|---|---|
| Mimi ordinary, 19Oct | 6 case accepted tích lũy với recovery; Playwright/Chromium synthetic app + model thật; không phải first-pass/all-Mimi certification |
| Mimi HARD | Benchmark riêng giữ toàn bộ report/gallery/media/backing **hiện có (AVAILABLE)** local, gồm failures/limitations; không trộn vào ordinary score |
| Outbox, 23Oct | 5/5 tích lũy qua các lượt API/IDB/PG/SW; khác mock success và physical quota proof |
| Responsive/PWA/compact, 25Oct | Viewport/synthetic runtime, safe-update/draft/lock; không đổi thành physical iPhone/Safari |
| Core/Mimi UI, 26–27Oct | Visible IAB, synthetic app + real API/PG + SDK double; later source delta phải nêu riêng |

Archive HARD có khoảng trống nguồn từ trước cleanup: `STUDY-PLAN-20-ORACLE.json` đã thiếu ở nguồn gốc nên không có bản để bảo tồn. Giữ rõ giới hạn provenance này; AVAILABLE không có nghĩa backing hoàn chỉnh hay HARD PASS, và khoảng trống cũ không tạo product regression hoặc acceptance gate mới.

QA Live là tên chung; provenance vẫn ghi transport thực (IAB/Playwright/Chrome/provider/synthetic). Receipt cũ chứng minh revision/case/config của nó; screenshot cũ không trở thành exact-head runtime proof.

Historical task/logs có trong Git tại baseline `48dc397663b145dab35994326af007dd0e26dcc7`. H14/Owner192 và runner source/tuple hardcode không tự launch/reseed/reset; reuse cần current grant/binding đúng guard. [Harness policy](../harness-policy.md) giữ authority semantics.
