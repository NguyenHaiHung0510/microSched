# Mimi context composition

Source: [context builder](../../backend/app/agent/context_builder.py), [service](../../backend/app/agent/service.py), [LangGraph](../../backend/app/agent/langgraph_runner.py), [tool registry](../../backend/app/agent/tools/registry.py). Tools gắn riêng ngoài messages; checkpoint/data không cấp quyền. Policy/schema prefix đứng trước mutable history/reference/authority. Model read/propose; server chỉ write sau frozen explicit Confirm.

[Operating contract](operating-contract.md) và [native routing](native-routing.md) là semantic source cho current route/context/Resume; old endpoint-certificate pool và conservative bytes-as-tokens refusal đã bị supersede.

## Composition và telemetry

Context ring dùng last attributable succeeded main-call prompt usage với receipt time. Cached tokens là subset của prompt usage; missing/inconsistent usage giữ unknown. Provider aggregate tokens/cache/cost khác request composition: serialized UTF-8 bytes được đo thành tám nonoverlapping buckets, chỉ sum tới tổng bytes. Không scale aggregate provider usage thành bịa per-category native tokens. Estimate phải ghi method/provenance, không thêm tokenizer dependency chỉ để hiển thị. Unassembled next request vẫn unknown; telemetry không thêm task/user/pending prose.

Configuration dùng durable validated policy/revision, edit draft và expected-revision CAS. Stale revision giữ draft để explicit reload/review. Manual per-model USD/M caps không phải market feed hoặc automatic cap raise/key-budget change. Composer giữ Unicode đầy đủ: default50000, finite1000–100000 codepoints, khác byte/context bounds.

## Capacity và recovery

272000 là **soft compaction trigger**,400000 là **operating input target**, không phải universal pre-send token proof hoặc byte gate. Model window, output planning reserve8192 và payload resource cap2MiB là các đại lượng riêng. Native main/helper dùng provider output defaults; planning reserve không phải generation cap hay financial reserve.

Machine-typed definite pre-generation context refusal cho phép tối đa một user-initiated native Resume/checkpoint successor. Generic400/413, outputlength, partial generation,429 và UNKNOWN là failure classes khác. Reconnect quan sát durable run; missing cost giữ liability, unknown phải reconcile trước redispatch. Fixed input/schema không compact được thì stop rõ ràng, không cắt nội dung để lách guard. Existing helper/run/deadline/no-progress quotas vẫn finite.

Opt-in local paid-QA reservation theo operating contract dùng shared configured context window và greater input/output manual cap, gồm reasoning; cache discount không được giả định. Production không dùng ledger riêng này. Provider default output và current gateway capacity không được diễn giải thành cam kết token/billing upper bound khác contract. No new call/budget/provider permission từ tài liệu.

## Qualification

Unit/SDK doubles chứng minh lifecycle, không live272K/400K/cache/provider quality. Native CAS/concurrency, browser/mobile/keyboard, cache/live, physical notifications, required CI và exact-head release/production cần receipt phù hợp. Policy storage dùng existing AppSetting; sắp xếp docs không thực thi migration hay thay policy.

## Dated illustrations

Hai ảnh gốc được Git LFS phân phối với SHA256/source metadata. Clone muốn xem local cần `git lfs pull`; pointer không phải binary. Đây là source/design explanation, không runtime/QA proof, không sửa ảnh cũ để giả current telemetry.

![Context builder, 2026-10-11 v1](../assets/mimi/context-builder-2026-10-11-v1.png)

[Metadata](../assets/mimi/context-builder-2026-10-11-v1.json), source43b50366a08f7ae84486ec6dc4fadcf2b8758b20, collection OFF/policyv2. Built-in imagegen từ source map; collection ON là conditional trong snapshot. PNG SHA256 `35d121544fdd0e335cc9f82fd0930fa511725a8006719536c26b936667959f76`.

![Original context design, 2026-10-13 v1](../assets/mimi/mimi-context-tooltip-owner-design-2026-10-13-v1.png)

[Original source metadata](../assets/mimi/mimi-context-tooltip-owner-design-2026-10-13-v1.source.json). Owner-supplied original; synthetic204000/category/cache values không phải product telemetry. Current interaction uses existing components/tokens/light/Nunito, click/touch/focus/hover và Escape/outside/X dismissal; portal không bị chat clip, technical inspector là surface riêng.
