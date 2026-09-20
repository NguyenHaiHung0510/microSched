# QA Agent framework — deterministic contracts, live model và dogfood

> **Trạng thái: DRAFT để Owner duyệt — 2026-09-20.** Đây là companion của
> [QA framework dùng chung](qa-framework.md), dành cho surface gọi AI agent/live model.
> File này không tự phê duyệt route, model, chi phí, dữ liệu thật hay production enablement.
> Mỗi slice phải có QA spec riêng; chưa có receipt thì là `NOT_RUN`, không phải `PASS`.

## 1. Vì sao cần companion riêng

QA giao diện thông thường kiểm một đầu vào tương đối ổn định đi qua code xác định. Agent thêm ba
nguồn bất định khác nhau:

1. **Model là probabilistic.** Cùng ý định có thể được diễn đạt khác nhau; exact-string assertion dễ
   vừa flaky vừa bỏ sót lỗi ngữ nghĩa.
2. **Run là phân tán và kéo dài.** Browser, API, worker, provider và database có thể kết thúc ở các
   thời điểm khác nhau. Một SSE connection đóng không chứng minh provider chưa làm gì.
3. **Model không phải authority.** Text/tool call chỉ là đề xuất không tin cậy. Quyền thực thi phải
   nằm ở server, qua validation, frozen confirmation và idempotent commit.

Vì vậy, một route probe thành công không chứng minh hành trình trong app; một UI mock đẹp không
chứng minh provider; một live answer đúng không chứng minh confirmation/write safety. Framework này
giữ các lớp đó tách biệt và buộc receipt chỉ claim đúng lớp đã quan sát.

## 2. Hai mặt phẳng kiểm thử

### 2.1 Deterministic plane — contract và safety

Đầu vào, clock, fixture, provider double và expected state được cố định. Plane này phải kiểm bằng
assertion chính xác:

- schema, prompt assembly, tool allowlist và server-issued execution lease;
- parser/normalizer, bounds, encryption, STANDARD/PRIVATE boundary;
- event ordering, durable state machine, replay cursor và terminal state;
- frozen preview, digest, nonce, expiry, source version và CAS;
- confirm/reject, idempotency, receipt, domain delta và crash recovery;
- retryable/definitive/unknown outcome; cancel, Resume và Reconcile;
- admission/token/cost limits trước khi egress.

Các safety invariant phải có negative test fail đúng lý do rồi mới pass sau khi restore. Không dùng
live model để “chứng minh” những invariant mà deterministic test có thể khóa chặt.

### 2.2 Probabilistic plane — behavior và quality

Live model được chấm theo **semantic rubric**, không theo một câu chữ vàng duy nhất. Mỗi case nêu:

- user intent và dữ kiện bắt buộc;
- điều model được phép/không được phép suy diễn;
- loại terminal hợp lệ: text, clarification hoặc đúng một typed proposal;
- lỗi gây fail: gọi tool thừa, tự thực thi, sai ngôn ngữ, bịa dữ kiện, vượt scope hoặc làm lộ dữ liệu;
- số mẫu/consecutive-run gate và seed/route metadata nếu provider hỗ trợ.

Một câu trả lời khác wording vẫn có thể PASS nếu đủ rubric. Ngược lại, lời văn tự nhiên nhưng sai
tool, sai boundary hoặc thiếu dữ kiện bắt buộc là FAIL.

### 2.3 Luật giao nhau

Live dogfood chỉ bắt đầu khi deterministic plane liên quan đã PASS ở exact commit đang chạy. Nếu live
run tìm thấy failure, phân loại failure trước; không nới assertion deterministic để hợp thức hóa output
probabilistic. Sau sửa lỗi, chạy lại focused deterministic regression rồi mới chạy lại live case.

## 3. Evidence ladder

| Lớp | Mục tiêu | Có egress/provider thật? | Có domain write? | Claim tối đa |
|---|---|---:|---:|---|
| A0 — static/offline preflight | Cấu hình, schema, bounds, fixture, isolation | Không | Không | `READY_FOR_ROUTE_CARD` |
| A1 — deterministic contract | State machine, parser, tool/confirmation/idempotency | Không | Chỉ throwaway DB | `CONTRACT_PASS` |
| A2 — synthetic full app | UI + API + SSE với provider double | Không | Chỉ fixture | `SYNTHETIC_E2E_PASS` |
| A3 — live route card | Callability/capability của một route đã pin | Có, bounded | Không | `ROUTE_CARD_PASS` |
| A4 — live full-app dogfood | Behavior thật qua app, stream và persistence | Có, bounded | Chỉ confirmation case đã duyệt | `LOCAL_LIVE_PASS` |
| A5 — production/device | Deploy, production config, thiết bị thật | Theo spec riêng | Theo quyền riêng | Chỉ claim khi đã chạy riêng |

Không được nhảy từ A3 sang kết luận A4. A4 local không chứng minh A5, và browser viewport không chứng
minh iPhone/Safari vật lý.

## 4. SSE và vòng đời run

### 4.1 Contract stream

- Unsafe start dùng authenticated `POST` + fetch streaming, giữ CSRF/origin checks; không đổi thành
  state-changing `GET` chỉ để dùng `EventSource`.
- Mỗi durable event có `run_id`, sequence đơn điệu, versioned/bounded kind, timestamp và payload đã
  lọc. `assistant.delta` phải được ráp theo thứ tự; không phát raw hidden reasoning, secret hoặc partial
  tool JSON.
- Heartbeat chỉ chứng minh observation channel còn sống, không phải model đang tiến bộ. Timer UI bắt
  đầu từ server acceptance và không suy đoán provider health.
- Browser là observer, không sở hữu run. Đóng panel, đổi tab/conversation, unfocus hoặc mất stream
  không tự cancel server work.
- Một observation stream hoạt động cho mỗi run. Reconnect dùng durable run ID + sequence cursor để
  replay; không tạo turn mới chỉ vì transport cũ đóng.

### 4.2 Assertion tối thiểu

Mỗi stream case phải đối chiếu cả ba view:

1. **Wire:** HTTP status/content type, event framing, thứ tự/sequence, heartbeat và terminal snapshot.
2. **Durable:** run/provider-call/event rows, encrypted content at rest, actual terminal/outcome.
3. **UI:** text ghép đúng một lần, elapsed/progress trung thực, controls đúng state, reload hội tụ.

`conversation.snapshot` hoặc terminal equivalent phải hội tụ với database. Duplicated/missing/out-of-
order event, stream kết thúc trước terminal snapshot mà UI báo thành công, hoặc reconnect tạo provider
call thứ hai đều FAIL.

### 4.3 Disconnect không phải failure class hoàn chỉnh

Khi transport đóng, outcome tạm thời là **ambiguous**. Hệ thống phải đọc durable run/provider identity:

- definitive failure có thể mở bounded Retry/Resume theo policy;
- `unknown` phải Reconcile trước mọi redispatch;
- succeeded nhưng result không thể phục hồi phải dừng an toàn, không tự đoán output;
- Owner cancel sau dispatch có thể để provider outcome `unknown`; không được relabel thành “không chạy”.

## 5. Frozen confirmation seam

Mô hình chuẩn của write-capable journey:

`model output → server parse/validate → canonical typed operation → frozen change set → Owner decision → server re-check → atomic mutation + receipt`

### 5.1 Trước confirmation

- Model tối đa đề xuất capability/tool đã cấp trong lease; không truyền SQL, arbitrary URL, secret,
  policy override hoặc `allow_private`.
- Server cấp ID, canonicalize args, khóa tool version, source/entity versions, digest, single-use nonce,
  expiry và idempotency scope. Model output không được làm authority envelope.
- Preview hiển thị đúng frozen payload. Revision tạo change set mới và stale/supersede bản cũ bằng CAS;
  text nói “đã sửa” không đủ để thay preview.
- Không domain mutation, side effect hoặc “optimistic write” xảy ra trước explicit Owner decision.

### 5.2 Tại confirmation

- Request bind exact change-set ID + digest + nonce + expected frontier/version.
- Backend đọc lại frozen server payload; không gọi model lại để tái tạo args.
- Re-check ownership, lease, expiry, source/entity freshness, privacy gate và tool policy.
- Mutation, execution receipt và refresh/recovery marker commit cùng transaction khi contract yêu cầu.
- Cùng idempotency + cùng content trả lại receipt cũ; cùng key khác content hoặc stale digest/frontier
  phải fail closed.

### 5.3 Bằng chứng bắt buộc

Receipt cần trước/sau domain snapshot, count provider calls, change-set digest/state, decision request,
execution receipt và reload result. PASS yêu cầu **đúng một** mutation. Screenshot preview không chứng
minh commit; database delta không chứng minh Owner đã nhìn đúng frozen payload nếu thiếu UI/wire proof.

## 6. Offline preflight và live route card

### 6.1 Offline preflight — tuyệt đối không egress

Preflight chạy trước khi bật live route và chỉ xuất giá trị không nhạy cảm/hash:

- exact Git commit, dirty state có liên quan, app/build/schema revision và QA spec version;
- `APP_ENV`, database class/host class và fixture manifest; fail nếu trỏ production hoặc data ngoài
  allowlist của spec;
- real-chat/provider flags, route mode, model, provider/allowlist, quantization, reasoning effort,
  tool-choice mode, ZDR/data-collection policy và public origin khi áp dụng;
- API key **presence only**; không in key, prefix, headers hoặc `.env`;
- context limit, serialized-input estimate, max output, run deadline, preview TTL, price caps, per-run và
  suite budgets; fail trước egress nếu không hữu hạn hoặc input + reserve vượt context;
- hash/version của system policy, tool schema, route policy và deterministic tests bắt buộc;
- clean isolation/cleanup plan, stable synthetic IDs và nơi lưu receipt đã scrub.

Kết quả là một manifest có timestamp + hash. Bất kỳ config/hash/commit nào đổi đều làm preflight cũ
hết hiệu lực.

### 6.2 Live route card — call nhỏ, không domain write

Route card trả lời “route cụ thể có đáp ứng capability contract lúc này không?”, không chấm toàn bộ
Mimi. Với evaluation lane, pin exact:

`(model, provider endpoint, quantization, reasoning effort, tool-choice, route-policy version)`

Fallback/manual reroute tắt. Card dùng prompt không nhạy cảm và ngân sách nhỏ để quan sát:

- authentication/availability và actual model/provider khớp pin;
- streaming framing, TTFT, terminal response/usage;
- text-only behavior và tool-schema compliance tối thiểu nếu route cần tools;
- parameter support, context/output bounds, ZDR/data policy và price-cap rejection;
- provider response/generation ID đủ cho reconciliation, nếu route contract yêu cầu.

Adaptive dogfood dùng card riêng: mọi endpoint trong allowlist phải đã đủ contract; record actual
provider mỗi call và FAIL nếu ra ngoài pool. Route card có `checked_at`, expiry ngắn do spec đặt và
không được dùng như bảo đảm tương lai.

## 7. Failure taxonomy

Mỗi failure có `stage`, `class`, `outcome`, `retry_policy`, `evidence completeness`; không gom mọi thứ
thành “AI lỗi”.

| Class | Ví dụ | Mặc định xử lý |
|---|---|---|
| `PREFLIGHT_CONFIG` | thiếu pin/cap/ZDR, sai DB class | dừng trước egress |
| `AUTH_PERMISSION` | key/session/CSRF/origin bị từ chối | definitive; không retry mù |
| `NETWORK_TRANSPORT` | DNS/TLS/connect/stream close | ambiguous nếu đã dispatch |
| `ROUTE_CAPABILITY` | model/provider/parameter/tool không hỗ trợ | route FAIL; reselect có phê duyệt |
| `PROTOCOL_STREAM` | SSE malformed, sequence gap, thiếu terminal | reconcile; không tạo turn mới |
| `MODEL_BEHAVIOR` | sai ngôn ngữ, không clarify, bịa dữ kiện | probabilistic case FAIL |
| `TOOL_CONTRACT` | tool/args sai schema, hơn một proposal | fail closed; không preview/write |
| `STATE_CONCURRENCY` | stale generation/frontier/source | conflict; refresh/revise |
| `CONFIRMATION_AUTHORITY` | digest/nonce/expiry/ownership sai | fail closed; zero write |
| `DOMAIN_COMMIT` | transaction/receipt/refresh marker lỗi | inspect commit truth trước retry |
| `BUDGET_LIMIT` | context, token, cost, deadline vượt cap | stop/pause rõ ràng; không truncate lén |
| `DATA_ISOLATION` | PRIVATE/secret/real identity lọt prompt/log | stop ngay; P0/P1 tùy blast radius |
| `UI_OBSERVABILITY` | fake progress, mất draft, success sai | UI case FAIL dù provider thành công |
| `EVIDENCE_GAP` | thiếu raw receipt/actual route/domain delta | `UNVERIFIED`, không PASS |

Canonical **provider outcome** chỉ dùng `succeeded`, `failed` hoặc `unknown`; khả năng thử lại là một
quyết định riêng trong `retry_policy`/run state, không phải provider outcome thứ tư. Timeout/connection
close sau dispatch mặc định là `unknown` cho đến khi có bằng chứng canonical khác.

## 8. Token, context, thời gian và chi phí

Mỗi suite live phải khóa trước một budget card do Owner/T1 có authority phê duyệt:

- context window và max output của route;
- max turns/tool calls/deadline cho run;
- max live calls và retries cho case/suite;
- input/output/cache/reasoning token caps nếu provider báo được;
- per-run và aggregate monetary cap, currency/unit và nguồn giá;
- stop threshold (ví dụ warning và hard stop) cùng người có quyền nâng cap.

Admission fail nếu serialized prompt + tool schema + output reserve vượt context; không truncate âm
thầm system/tool policy hoặc lịch sử cần cho safety. Receipt dùng usage/cost do provider/purchasing API
trả về, kèm source và checked-at. Estimate phải ghi `ESTIMATED`, không trộn với billed cost.

Cache hit, TTFT, throughput và output/reasoning volume là các số riêng; cache hit tốt không tự chứng
minh rẻ hoặc đúng. Budget/deadline stop là một terminal trung thực, không phải product PASS.

## 9. Isolation và dữ liệu

- Mặc định dùng STANDARD synthetic/disposable data, conversation mới và stable manifest-owned IDs.
- Local DB là throwaway Postgres hoặc QA data đã được contract cho phép. Neon Restore/Sync/create/delete
  vẫn Owner-operated; chưa có xác nhận sync thì không chạy high-fidelity develop QA.
- Live provider chỉ nhận assembled payload mà spec cho phép. Ghi manifest nguồn/context đã chọn; nội
  dung nhìn thấy trong right rail không mặc nhiên là model context.
- Không dùng browser profile thật như fixture; không đọc cookie/password/autofill/history/profile store.
- Không đưa secret, auth headers, API key, real email/identity hoặc PRIVATE content vào prompt, log,
  screenshot, trace hay committed artifact.
- Mỗi case cô lập conversation/run/client-id/idempotency namespace. Retry/Resume/Reconcile phải dùng
  đúng identity đã ghi, không tái dùng key giữa case.
- Cleanup chỉ xóa exact manifest-owned synthetic rows/artifacts sau khi receipt đã giữ; mismatch hoặc
  unowned dependency thì giữ và báo. Logout và đóng task tabs sau browser QA.

## 10. Receipt và verdict

Mỗi case ghi tối thiểu:

- case/spec version, exact commit, UTC/local timestamp, actor và environment class;
- preflight manifest hash, route-card ID/expiry, route mode và actual model/provider;
- sanitized fixture/input, conversation/run/provider-call/change-set/receipt IDs;
- event sequence hoặc bounded raw excerpt, terminal state/outcome, retry/reconcile count;
- prompt/tool-policy hashes, token/cache/cost/timing usage và budget remaining;
- expected rubric, observed output/domain delta, cleanup và `PASS`/`FAIL`/`NOT_RUN`/`BLOCKED`.

`PASS` chỉ khi mọi mandatory assertion của case có raw evidence và không vi phạm hard boundary.
`FAIL` dùng khi đã chạy và observed behavior sai. `BLOCKED` dùng khi prerequisite/external route ngăn
chạy. `NOT_RUN` là chưa chạy. Aggregate suite không được PASS nếu required case là FAIL/BLOCKED/NOT_RUN;
exception chỉ hợp lệ khi chính approved spec định nghĩa gate đó và vẫn giữ nguyên nhãn thật.

## 11. Template tối thiểu cho QA spec Agent

Một spec cụ thể nên có:

1. status/authority, scope và non-goals;
2. exact capabilities/tools/data boundary;
3. evidence ladder/lane áp dụng;
4. prerequisites + offline preflight;
5. route-card matrix;
6. deterministic contract cases;
7. probabilistic journeys và semantic rubric;
8. SSE/state/failure/budget/isolation matrices;
9. case IDs, execution order, stop/re-plan conditions;
10. receipt schema, PASS/FAIL aggregation và cleanup.

Outline đầu tiên áp dụng framework này là
[Mimi P1 Live Dogfood QA spec](qa-specs/qa-mimi-p1-live-dogfood.md).
