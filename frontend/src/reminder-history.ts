export type HistoryRow = {
    origin: string;
    source_kind: string;
    occurrence_ref: {
        origin: string;
        id: string;
    };
    source_ref: {
        kind: string;
        id: string;
    };
    occurrence_at: string | null;
    occurrence_on: string | null;
    time_precision: string;
    time_basis: string;
    status: string;
    title: string;
    body: string;
    handled_at: string | null;
    is_private: boolean;
    can_open: boolean;
    can_handle: boolean;
};
export type HistoryPage = {
    items: HistoryRow[];
    next_cursor: string | null;
    has_more: boolean;
    private_notice: {
        title: string;
        body: string;
    } | null;
};
export type HistoryBatch = {
    id: string;
    selected_count: number;
    cutoff: string;
    expires_at: string;
    filter: Record<string, unknown>;
    scope_visible: boolean;
    result: {
        selected_count: number;
        new_count: number;
        already_count: number;
    } | null;
};
export const historyIdentity = (row: HistoryRow) => row.occurrence_ref.origin + ':' + row.occurrence_ref.id;
export const historyStatus: Record<string, string> = { pending: 'Đang chờ', sending: 'Đang gửi', sent: 'Đã gửi tới dịch vụ', accepted: 'Có thiết bị được dịch vụ nhận', unknown: 'Chưa rõ kết quả gửi', retryable: 'Đang chờ thử gửi lại', expired: 'Đã hết hạn gửi', suppressed: 'Không gửi', not_requested: 'Chưa yêu cầu gửi thiết bị', missed: 'Lỡ thời điểm', needs_reschedule: 'Cần đặt lại giờ', no_device: 'Chưa có thiết bị nhận', failed: 'Chưa xác nhận gửi thành công', cancelled: 'Đã huỷ', exhausted: 'Đã hết lượt gửi' };
export function historyDay(day: string) { return day ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'full', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(day + 'T12:00:00+07:00')) : 'Chưa rõ ngày nhắc'; }
export function historyTime(row: HistoryRow) { if (!row.occurrence_at)
    return row.occurrence_on ? 'Không lưu giờ' : 'Không lưu thời điểm'; const time = new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(row.occurrence_at)); return time + (row.time_basis === 'recorded_only' ? ' · lúc ghi nhận' : ''); }
