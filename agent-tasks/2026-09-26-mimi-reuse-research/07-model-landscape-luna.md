# Landscape model cho Mimi: deterministic baseline, GPT-6 Luna và các họ thay thế

Ngày chốt nguồn: 2026-09-26 (Asia/Saigon). Đây là nghiên cứu tài liệu, không gọi model/API, không dùng key, không chạy benchmark, không thay route. Giá, latency, availability và chính sách provider thay đổi; số OpenRouter dưới đây là snapshot đọc ngày 2026-09-26, không phải SLA hoặc kết quả traffic microSched.

## Tóm tắt điều hành

Chưa có bằng chứng để chọn champion hoặc bật thêm một model trong production. Phải tách hai quyết định:

1. **Model chính cho Mimi/MIDEX-mini:** so end-to-end task completion trên hội thoại tiếng Việt, tool use, output validation, cost tổng và privacy. Đối chứng gồm deterministic/application path, model incumbent, GPT-6 Luna, Gemini 3.8 Flash và Qwen3.5 Flash; có thể thêm một model quality comparator nếu Owner muốn và privacy gate cho phép. Jev không phải general agent, không thay vòng này.
2. **Triage/typed-decision tùy chọn:** chỉ có lý do tồn tại nếu thực sự giảm cost-per-correct-task, lỗi điều hướng hoặc công sức review mà vẫn thỏa privacy/latency. Đối chứng bắt buộc là không gọi model thêm: deterministic/Pydantic fast path hoặc structured output trong lượt model chính hiện có. Jev là một specialist candidate, không phải khuyến nghị.

Điểm giao thức quan trọng: model hiện hành là **GPT-6 Luna**, không phải GPT-5.6 Luna. Tài liệu OpenAI khuyên Responses cho function calling/tools; Chat Completions chỉ hỗ trợ function calling với reasoning_effort="none". Vì Mimi hiện dùng chat-completion-style transport, chọn Luna cùng effort có reasoning không phải thay model-only: cần đánh giá adapter/contract Responses. Giữ Chat Completions với effort none khả thi theo docs nhưng chưa chứng minh đủ năng lực Mimi.

## Câu hỏi sản phẩm và ranh giới

**Quan sát trong code/contract tại worktree 065-mimi-p1c-context-loop:** Mimi là hội thoại tự nhiên, chủ yếu tiếng Việt; model không phải nguồn thẩm quyền. Tools bounded/allowlisted gồm query, aggregate, inspect-batch và tạo candidate preview. Candidate không ghi dữ liệu; write chỉ sau luồng xác nhận/server được phép. Ngày giờ được chuẩn hóa trong ứng dụng theo Asia/Ho_Chi_Minh/UTC. Route hiện parse tool calls và structured terminal result qua giao thức OpenAI-like chat completion.

Nguồn local: backend/app/agent/policy/mimi-standard-v1.md; backend/app/agent/tools/registry.py; backend/app/agent/tools/task_reads.py; backend/app/agent/openrouter.py; task contract nêu live route mặc định off tới khi có route-card/privacy/fallback được duyệt. Đây là bằng chứng code/contract trong checkout, không xác nhận deployment hoặc runtime.

**Phù hợp để tự động hóa có giới hạn:** phân loại intent/độ mơ hồ; chọn read-only answer, hỏi lại, hoặc đề xuất tool đọc; xác định đủ trường để lập preview; route lệnh rõ ràng sang deterministic fast path; gắn nhãn/score để quan sát hoặc ưu tiên review. Tất cả lựa chọn qua enum/schema và server policy.

**Không giao cho model quyết định cuối:** authorization, xác nhận hành động, ghi dữ liệu, permission/security, tính đúng của số/ngày/giờ quan trọng, hoặc timeout có tác động thời gian. Model có thể đề xuất “cần xác nhận/cần hỏi”; server sở hữu quyền và semantics. Parser ngày/số dùng code/domain rules. Timeout không chứng minh request không xảy ra: kiểm tra trạng thái thực trước retry để tránh lặp side effect. Khi ý định/lịch mơ hồ, hỏi người dùng; không fail-open sang thao tác mạnh hơn.

## So sánh các họ ứng viên

| Họ / vai trò để eval | Giao thức và khả năng được tài liệu hiện hành nêu | Giá snapshot / tín hiệu nhanh | Tiếng Việt, privacy và unknowns |
|---|---|---|---|
| **Không thêm model: deterministic/Pydantic + domain resolver** | App kiểm tra schema/enum/date/types; route lệnh rõ bằng rule; reject/ask khi unknown. Không endpoint/tool-call/output token. | Inference cost bằng 0; latency chủ yếu app-local. Cần tính engineering/maintenance và false reject/route trong eval. | Không có language-coverage issue cho enum/literal, nhưng không hiểu paraphrase/multi-intent. Hợp với permission, date arithmetic, required fields, state transitions, authorization. Baseline và lớp sau model, không thay hiểu ngôn ngữ. |
| **Incumbent generative model, structured output/tool call trong lượt có sẵn** | Giữ model/route hiện tại làm baseline thực. Validate schema ở server; model chỉ đề xuất tool/candidate, server áp allowlist và quyền. Không thêm round trip. | Phải lấy giá/route thật từ config và billing; nghiên cứu này không đo. Đo incremental prompt/output tokens và failures. | Có context hội thoại hiện tại; có thể tăng token/error. Fallback deterministically khi invalid/timeout. Đây là comparator thiết yếu của sidecar. |
| **OpenAI GPT-6 Luna — general model, candidate primary hoặc structured step** | Model docs: function calling + Structured Outputs. Responses được khuyến nghị cho tools/function calling. Chat Completions chỉ function-call khi reasoning_effort="none"; effort gồm none, low, medium, high, xhigh, max. Nếu cần tools cùng reasoning, route hiện tại có thể cần adapter Responses. | OpenAI Standard listed: $0.10/M input, $0.01/M cached input, $0.125/M cache writes, $0.50/M output; >272K input có bậc giá khác. Batch/Flex giảm 50%, Fast gấp 2 khi phù hợp, không lấy làm default. OpenRouter hiển thị OpenAI, Azure, Bedrock routes; directory/weighted aggregate không đảm bảo invoice của account/route. | Docs nêu multilingual nói chung, không có Mimi/Vietnamese task benchmark. Phải test tiếng Việt có dấu/không dấu, viết tắt/code-switch. OpenAI API không đồng nghĩa ZDR: kiểm tra data controls theo account/project/endpoint. Nếu qua OpenRouter phải xác minh provider thực. Model docs không đưa latency/SLA đủ để dự báo. |
| **Google Gemini 3.8 Flash — general agent model** | Gemini API có function calling và structured output; cần kiểm tra schema subset và envelope. AI Studio và Vertex là route/privacy khác nhau. | Google AI Studio intro $0.75/M input + $3.75/M output đến hết 2026-12-31; từ 2027-01-01 standard $1.50/$7.50. OpenRouter snapshot p50 ~1.40s AI Studio, 2.90s Vertex; availability rolling 3d 99.43%. Động, không phải benchmark độc lập/SLA. | General multilingual docs không chứng minh Vietnamese intent/date quality. Privacy khác nhau theo API/product; Vertex có governance riêng, AI Studio retention khác. Pin provider/project/region và điều khoản chính xác trước khi gửi hội thoại. Intro price là promo có hạn. |
| **Alibaba Qwen3.5 Flash — general low-cost/low-latency candidate** | OpenRouter snapshot nêu 1M context; listing có capability tool/JSON nhưng phải xác nhận lại trên exact API route. | OpenRouter: $0.065/M input, $0.26/M output; p50 0.65s; rolling 3d availability 99.72%; một Alibaba Cloud International provider trong snapshot. Đây không phải first-party universal price/SLA. | Vendor công bố multilingual breadth, không có evidence độc lập về Mimi tiếng Việt. Route retention/ZDR/data location và eligibility phải xác minh; provider đơn làm tăng route/fallback risk. Candidate cost-sensitive chỉ nếu privacy gate qua. |
| **TypeSafe Jev 1.13 — specialist typed decision, không assistant tổng quát** | TypeSafe mô tả primitives Choice, Score, Noul (boolean-like probability). OpenRouter listing nói text input, structured decisions output; model page nêu decision endpoint /api/alpha/decisions, không phải OpenAI chat tool cycle. Cần adapter/contract riêng; không sinh hội thoại, tự gọi tools hay giải thích tự nhiên. | OpenRouter 9/26: $0.042/M input, $0/M output; 32K context; p50 0.21s; availability displayed 100%/3 ngày trong snapshot. Input 1K token tương đương $0.000042 theo listing, chưa tính routing/platform overhead. “Free output” không có nghĩa request miễn phí. | Chưa thấy Vietnamese quality/calibration, date/number handling hoặc independent Mimi eval. TypeSafe là provider duy nhất trong listing; directory privacy không chứng minh route endpoint ZDR, retention/deletion/region/subprocessors. Cần xác nhận trực tiếp trước khi gửi hội thoại. |
| **Specialist classification APIs (Cohere/AWS/Google NLP)** | AWS Comprehend custom classification đòi labeled training; language matrix không liệt kê Vietnamese cho custom classification. Google Natural Language có predefined taxonomy, không phải Mimi intent schema; support tùy endpoint/task (sentiment tiếng Việt không đồng nghĩa intent classification). Cohere /v1/classify hiện đánh dấu deprecated. | Không shortlist giá/tốc độ do mismatch task/language, không kết luận về mọi sản phẩm specialist. | Xem lại nếu task chuyển thành sentiment/entity hoặc taxonomy cố định được hỗ trợ. Scan này không xác minh được API specialist hiện đại nào phù hợp đồng thời Jev-shaped decision + Vietnamese + Mimi privacy. |

OpenRouter là directory/route telemetry, không phải nguồn độc lập về quality/privacy. Không chọn theo p50 nhanh nhất, availability snapshot, marketing benchmark hoặc cached-weighted aggregate. Cần exact provider + model ID + API/protocol + data-control route, rồi xác minh thực tế.

## GPT-6 Luna: phân tầng lựa chọn

Sửa nhầm tên: **GPT-6 Luna**, không phải GPT-5.6 Luna. OpenAI changelog ghi Luna release ngày 2026-09-22; model page mô tả model hiệu quả cho high-volume/focused tasks. Đây là candidate benchmark về cost/capability, không mặc định là model tốt hơn cho Mimi.

- Nếu cần function calling cùng reasoning effort khác none, theo docs dùng Responses API; cần đánh giá transport adapter so với route chat hiện tại.
- Nếu giữ Chat Completions, function calling chỉ được tài liệu hỗ trợ khi reasoning_effort="none". Đánh giá riêng tool-choice, schema, invalid/partial output, latency và Vietnamese task completion ở chế độ này.
- Nếu chỉ cần JSON, Structured Outputs giúp format/schema, không đảm bảo semantic correctness.
- Model choice không trao quyền chọn operation. App vẫn sở hữu registry, auth, temporal logic, validation, preview, confirmation và writes.

## Privacy, fallback, lock-in và fail policy

Data eligibility là gate trước quality/cost. Dùng synthetic fixtures. Với từng hosted candidate, chốt đúng model version, aggregator/direct endpoint, provider, region, retention/training settings, abuse logs, ZDR eligibility, subprocessors, prompt caching và failover route. Nếu aggregator tự chọn provider, allowlist; không failover sang provider chưa qua gate. Directory claims “ZDR/zero retention” chỉ là lead, không phải approval.

**Fail closed:** malformed schema, unknown enum, confidence/calibration chưa đạt, contradictory/multi-intent, ambiguous date/time, thiếu dữ liệu bắt buộc, security/permission request, confirmation/write request, provider route không rõ, hoặc timeout sau non-idempotent action. Closed nghĩa hỏi/review/không thực thi, không nhất thiết từ chối hội thoại.

**Fail open có giới hạn:** classifier unavailable có thể tiếp tục primary assistant theo policy hoặc hỏi thêm; không map lỗi thành create/write/authorize. Query task chỉ chạy sau khi server xác thực schema/tenant/filter. Create candidate chỉ preview; timeout/duplicate cần idempotency/state-check phía server.

Để giảm lock-in, định nghĩa interface nội bộ trung lập vendor. DecisionRequest: schema version, task enum, minimized relevant text/context, allowed action candidates, locale, correlation id. DecisionResult: enum/action suggestion, typed args nếu schema cho phép, abstain/needs-clarification, score chỉ khi semantics provider cho phép, reason code, exact model/provider/route/version, usage/latency, validation status. Không gọi raw score là xác suất khi chưa calibration; không trả quyền/auth/tool execution. Adapter map từng provider envelope vào cùng enum/validator/terminal behavior.

Fallback cần hữu hạn: timeout/5xx/rate limit → deterministic parse/route nếu match chắc chắn, nếu không hỏi lại; không retry vô hạn. Malformed/unsafe → reject + ask/review. Privacy mismatch → không gửi request; dùng rule path hoặc hỏi. Không raw private text trong telemetry.

## Eval đề xuất trước model/route decision

Hai track độc lập nhưng dùng chung taxonomy:

**A. Overall Mimi / MIDEX-mini:** deterministic + incumbent + GPT-6 Luna (Chat Completions/none nếu test route cũ, và/hoặc Responses với tool reasoning) + Gemini 3.8 Flash + Qwen3.5 Flash. Haiku hoặc quality comparator chỉ thêm nếu Owner muốn và provider/privacy đủ điều kiện. Test trọn turn: hiểu lời Việt → chọn tool → validate args → query → trả lời/hỏi lại → preview. Success chỉ khi qua tất cả product gates.

**B. Triage sidecar:** deterministic classifier; incumbent structured decision trong cùng lượt; Jev 1.13; một general low-cost model dùng JSON/function call. So sidecar với no-sidecar. Đo extra-call latency/cost và downstream tokens/failures tiết kiệm; nếu không chặn lỗi có ý nghĩa hoặc UX chậm hơn thì bỏ.

Fixtures tổng hợp, held-out theo nhóm, không dùng production text: Vietnamese có/không dấu, viết tắt/chat, code-switch; multi-intent; câu mơ hồ; “chiều mai/thứ 2” và timezone; thiếu thông tin; number/recurrence; quoted/prompt-injection trong task/note; yêu cầu xóa/sửa/đặt lịch/confirm; quyền sai tenant; read-only vs preview. Lịch cần deterministic oracle; classifier không tự tính ngày. Giữ test split cố định; tune threshold trên validation, không leak.

Metrics: exact task completion theo product contract; intent/action confusion; false tool-call/preview/unauthorized/write/confirm attempt (zero-tolerance gate); correct abstain/clarification; invalid schema/tool args; unsafe-instruction resistance; date/number errors; Vietnamese subtype breakdown; calibration chỉ nếu score có semantics và được calibration; retry/fallback; API error/empty response; per-route p50/p95 end-to-end latency; actual billed input/output/cached tokens; total billed cost; cost per correctly completed task; blinded UX review. Ghi model version, effort, API, provider/region, schema, prompt hash, billing tier và ngày đo. Không dùng benchmark marketing thay eval này.

### Cost/latency break-even (công thức, không phải kết quả)

Cost/correct = tổng billed cost (mọi calls, retries, fallback và failed cases) / số case pass mọi task + safety gate.

C_sidecar = C_triage + C_primary_after_triage + C_retries/fallbacks.
C_base = C_primary_direct + C_retries/fallbacks.

Chỉ thêm sidecar nếu giảm cost-per-correct hoặc lỗi/review đủ giá trị để bù chi phí, cùng lúc đạt latency/privacy gate. Nếu sidecar chạy trước rồi vẫn gọi primary với prompt/output như cũ, mặc định tăng cost và cộng round trip; nó phải giảm prompt size, retries, generated tokens, hoặc tránh được primary call. Jev listing $0.042/M input nghĩa 1K token khoảng $0.000042; GPT-6 Luna direct Standard 1K input + 100 output khoảng $0.00015, trước cache/context/fallback. Đây là phép tính từ listed rates, không dự đoán usage/effective cost/chất lượng. Jev 0.21s, Qwen 0.65s và Gemini 1.40s là directory p50 snapshots; end-to-end còn queue, prompt/response size, retries và tool latency. Cần paired measurement cùng environment.

## Nguồn đã đọc (2026-09-26)

Local evidence: backend/app/agent/policy/mimi-standard-v1.md; backend/app/agent/tools/registry.py; backend/app/agent/tools/task_reads.py; backend/app/agent/openrouter.py; task contract tại agent-tasks/2026-09-26-mimi-reuse-research/. Đây là source checkout, chưa đối chiếu production.

- OpenAI, GPT-6 Luna model doc: https://developers.openai.com/api/docs/models/gpt-6-luna
- OpenAI, model guidance (Responses vs Chat Completions/reasoning/tools): https://developers.openai.com/api/docs/guides/latest-model
- OpenAI, pricing (short/long context and processing tiers): https://developers.openai.com/api/docs/pricing
- OpenAI, API changelog (GPT-6 Luna release): https://developers.openai.com/api/docs/changelog
- OpenAI, data controls overview (verify exact account/route): https://developers.openai.com/api/docs/guides/your-data
- OpenRouter, GPT-6 Luna route listing: https://openrouter.ai/openai/gpt-6-luna
- Google AI, Gemini 3.8 Flash current model/pricing notice: https://ai.google.dev/gemini-api/docs/latest-model
- Google AI, Gemini models docs: https://ai.google.dev/gemini-api/docs/models
- Google AI, function calling and structured output: https://ai.google.dev/gemini-api/docs/function-calling and https://ai.google.dev/gemini-api/docs/structured-output
- OpenRouter, Gemini 3.8 Flash provider/time-window telemetry: https://openrouter.ai/google/gemini-3.8-flash
- Google Cloud Vertex AI data governance (verify exact product/region): https://cloud.google.com/vertex-ai/generative-ai/docs/data-governance
- OpenRouter, Qwen3.5 Flash provider/price/telemetry: https://openrouter.ai/qwen/qwen3.5-flash-02-23
- Qwen, Qwen 3.5 announcement/multilingual vendor claims: https://qwen.ai/blog?email_hash=23463b99b62a72f26ed677cc556c44e8&id=qwen3.5
- TypeSafe, System One typed primitives: https://docs.typesafe.ai/concepts/system-one
- OpenRouter, Jev 1.13 listing: https://openrouter.ai/typesafe/jev-1.13
- OpenRouter, provider privacy/retention listings (not route approval): https://openrouter.ai/providers
- AWS, Comprehend supported-language matrix: https://docs.aws.amazon.com/comprehend/latest/dg/supported-languages.html
- Google Cloud Natural Language language matrix: https://docs.cloud.google.com/natural-language/docs/languages
- Google Cloud Natural Language text-classification API/taxonomy: https://docs.cloud.google.com/natural-language/docs/classifying-text
- Cohere, Classify API (marked deprecated): https://docs.cohere.com/reference/classify

## Confidence và unknowns

**Cao:** checkout contract/code observations; OpenAI effort/protocol distinction; published direct list prices; Jev documented primitives/input-output; specialist language/API mismatch as documented.

**Trung bình/thấp:** directory price/latency/availability snapshots (dynamic); vendor multilingual claims; inference về Vietnamese workload quality.

**Chưa biết / phải xác minh:** incumbent model/provider/effort và per-task baseline; Vietnamese quality/calibration; exact tool-choice/strict schema conformance per endpoint; Jev decision request/response contract, exact route ZDR/retention/deletion/subprocessors; account-level ZDR eligibility; Gemini/Qwen provider retention/region; actual p95/errors; token distribution/caching/real cost; Responses adapter fit; measurable downstream benefit of triage. Không provider call/key/code modification/production traffic/end-to-end eval nào đã thực hiện.

## Phán đoán nghiên cứu (không phải quyết định Owner)

Chưa có căn cứ nói “Jev nên dùng” hoặc “GPT-6 Luna thắng”. Giữ deterministic/application checks làm safety/fast-path baseline; model incumbent structured output là no-extra-call comparator; shortlist family cho overall Mimi là GPT-6 Luna, Gemini 3.8 Flash, Qwen3.5 Flash; Jev chỉ ở track triage nếu privacy route qua gate. Với GPT-6 Luna, Chat Completions/none và Responses/tools-with-reasoning là hai cấu hình khác nhau cần eval, không phải mặc định thắng/thua. Không gọi production model cho đến khi có exact route/privacy evidence, synthetic eval evidence, cost/latency receipt và quyết định theo charter.
