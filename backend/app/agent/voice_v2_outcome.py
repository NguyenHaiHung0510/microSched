"""Fixed scalar outcomes for browser and model; no raw task/provider content."""

from dataclasses import dataclass

MESSAGES = {
    "voice_action_committed": "Đã áp dụng thay đổi; kết quả đã được lưu.",
    "voice_action_undone": "Đã hoàn tác thay đổi; kết quả đã được lưu.",
    "voice_manual_preview": "Đã chuẩn bị bản xem trước. Hãy kiểm tra và xác nhận trong ứng dụng.",
    "voice_request_incomplete": (
        "Chưa áp dụng: phương án chưa khớp toàn bộ yêu cầu. "
        "Hãy nói rõ đủ các việc hoặc sửa yêu cầu."
    ),
    "voice_plan_invalid": "Chưa áp dụng: phương án chưa hợp lệ. Hãy nói lại thay đổi cần làm.",
    "voice_preview_pending": "Chưa áp dụng: đang có bản xem trước chờ bạn duyệt trong ứng dụng.",
    "voice_source_changed": "Chưa áp dụng: dữ liệu đã thay đổi. Cần đọc lại trước khi tiếp tục.",
    "voice_undo_unavailable": (
        "Chưa hoàn tác: thay đổi được chọn không đủ điều kiện hoặc đã có chỉnh sửa mới hơn."
    ),
    "voice_selection_stale": "Chưa áp dụng: lựa chọn chưa khớp dữ liệu hiện tại. Cần chọn lại.",
    "voice_spoken_intent_unproven": "Chưa áp dụng: chưa rõ lệnh nói hiện tại. Hãy nói lại.",
    "voice_turn_expired": "Chưa áp dụng: lượt nói không còn hiệu lực.",
    "voice_action_not_authorized": "Chưa áp dụng: phiên không còn đủ quyền cho thao tác này.",
    "voice_result_ambiguous": (
        "Chưa xác định kết quả. Hãy kiểm tra receipt trong ứng dụng trước khi làm lại."
    ),
    "voice_plan_rejected": "Chưa áp dụng: giao dịch không thành công. Hãy xem lại trong app.",
}

# Fixed scalar vocabulary only. No exception text, field values or speech enters
# either transport. A missing proposal field does not prove the caller omitted it.
DETAILS = {
    "invalid_shape": ("clarify_plan_shape", "Chưa áp dụng: cấu trúc phương án chưa hợp lệ."),
    "multiple_proposals": (
        "one_whole_plan_after_fresh_speech",
        "Chưa áp dụng: Mimi gửi nhiều phương án; cần một phương án cho cả nhóm.",
    ),
    "insufficient_data": (
        "identify_missing_plan_data",
        "Chưa áp dụng: phương án thiếu dữ kiện bắt buộc. Cần xác định phần còn thiếu.",
    ),
    "receipt_missing": ("inspect_saved_results", "Chưa có kết quả đã lưu để hoàn tác."),
    "receipt_not_exposed": (
        "identify_exposed_receipt",
        "Chưa hoàn tác: chưa xác định được kết quả đã lưu mà bạn muốn chọn.",
    ),
    "receipt_stale": (
        "inspect_saved_results",
        "Chưa hoàn tác: dữ liệu đã đổi sau lần lưu đó; nói lại không bỏ qua được kiểm tra này.",
    ),
    "latest_inverse": (
        "identify_exposed_receipt",
        "Kết quả mới nhất đã là một lần hoàn tác. Cần chỉ rõ kết quả bạn muốn đảo lại.",
    ),
    "receipt_unavailable": (
        "inspect_saved_results",
        "Kết quả được chọn chưa đủ bằng chứng để hoàn tác; hãy kiểm tra kết quả đã lưu.",
    ),
    "activity_timing": (
        "fresh_speech_after_ready",
        "Chưa áp dụng: chưa ghép được thao tác với cửa sổ âm thanh hiện tại.",
    ),
    "activity_signal": (
        "fresh_speech_after_ready",
        "Chưa áp dụng: cửa sổ âm thanh hiện tại chưa có tín hiệu đủ để gắn thao tác.",
    ),
    "activity_tainted_epoch": (
        "fresh_speech_after_ready",
        "Chưa áp dụng: lượt kết nối đang cần đồng bộ; hãy chờ sẵn sàng rồi nói lại.",
    ),
    "activity_cancelled": (
        "fresh_speech_after_ready",
        "Chưa áp dụng: lượt nói đã bị ngắt hoặc hủy.",
    ),
}


@dataclass(frozen=True)
class VoiceActionOutcome:
    status: str
    reason: str
    reset_context: bool = False
    receipt_id: str | None = None
    receipt_ref: str | None = None
    subreason: str | None = None

    def __post_init__(self):
        if self.subreason is not None and self.subreason not in DETAILS:
            raise ValueError("voice_outcome_detail_invalid")

    def detail(self):
        return (
            {"detail": {"code": self.subreason, "next_step": DETAILS[self.subreason][0]}}
            if self.subreason
            else {}
        )

    def event(self):
        return {
            "type": "action_updated",
            "status": self.status,
            "reason": self.reason,
            "message": DETAILS[self.subreason][1] if self.subreason else MESSAGES[self.reason],
            **({"receipt_id": self.receipt_id} if self.receipt_id else {}),
            **self.detail(),
        }

    def model_result(self):
        return {
            "status": "preview_required" if self.status == "preview" else self.status,
            "reason": self.reason,
            "final": True,
            **self.detail(),
            **(
                {"applied": self.status in {"applied", "undone"}}
                if self.status != "unknown"
                else {}
            ),
            **({"receipt_ref": self.receipt_ref} if self.receipt_ref else {}),
        }


def committed(status, *, receipt_id=None, receipt_ref=None):
    return VoiceActionOutcome(
        status,
        {
            "applied": "voice_action_committed",
            "undone": "voice_action_undone",
            "preview": "voice_manual_preview",
        }[status],
        receipt_id=str(receipt_id) if receipt_id else None,
        receipt_ref=receipt_ref,
    )
