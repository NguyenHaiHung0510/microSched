import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CircleCheckIcon, InfoIcon, TriangleAlertIcon, OctagonXIcon, Loader2Icon } from "lucide-react"

// Bản CLI sinh ra đọc theme qua `useTheme()` của next-themes và mặc định là
// `"system"`. Dự án này light-only (ui-brief §6.7) và KHÔNG có ThemeProvider, nên
// `useTheme()` trả về undefined ⇒ rơi đúng vào `"system"` ⇒ iPhone đang để dark
// mode sẽ thấy toast NỀN ĐEN giữa một giao diện sáng. Chốt cứng `light` và gỡ
// next-themes; ngày nào làm dark mode thì thêm lại (ui-brief §7).
const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="light"
      // Radix modal (qua react-remove-scroll) đặt `pointer-events: none` lên
      // `body` khi có Dialog mở; toast là con của body nên kế thừa và không
      // nhận chạm dù z-index cao hơn overlay. Cố định `pointer-events: auto`
      // trên chính khung toast để nút action (vd Hoàn tác sau khi dời việc từ
      // dialog lịch) vẫn bấm được khi dialog đang mở.
      className="toaster group pointer-events-auto"
      icons={{
        success: (
          <CircleCheckIcon className="size-4" />
        ),
        info: (
          <InfoIcon className="size-4" />
        ),
        warning: (
          <TriangleAlertIcon className="size-4" />
        ),
        error: (
          <OctagonXIcon className="size-4" />
        ),
        loading: (
          <Loader2Icon className="size-4 animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
