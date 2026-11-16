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
        "Chưa hoàn tác: thay đổi gần nhất không đủ điều kiện hoặc đã có chỉnh sửa mới hơn."
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


@dataclass(frozen=True)
class VoiceActionOutcome:
    status: str
    reason: str
    reset_context: bool = False
    receipt_id: str | None = None
    receipt_ref: str | None = None

    def event(self):
        return {
            "type": "action_updated",
            "status": self.status,
            "reason": self.reason,
            "message": MESSAGES[self.reason],
            **({"receipt_id": self.receipt_id} if self.receipt_id else {}),
        }

    def model_result(self):
        return {
            "status": "preview_required" if self.status == "preview" else self.status,
            "reason": self.reason,
            "final": True,
            "applied": self.status in {"applied", "undone"},
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
