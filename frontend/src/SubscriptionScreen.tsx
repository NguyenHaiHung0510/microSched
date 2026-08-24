import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { apiRequest } from '@/api'
import { toVietnamDateTimeInput, vietnamInputToIso } from '@/calendar-ui'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { hasAppHistory, navigate, queryParams, useLocation } from '@/lib/route'
import { uuidv7 } from '@/lib/uuidv7'
import { standardRefetchInterval } from '@/query-polling'
import {
  addPeriod,
  daysLeftLabel,
  formatShortDate,
  periodLabel,
  renewSummary,
  statusLabel,
  subscriptionInvalidationKey,
  subscriptionQueryKey,
  subscriptionTrackers,
  todayVn,
  useSubscriptionWrites,
  type PeriodUnit,
  type RenewPayload,
  type SettingsItem,
  type Subscription,
  type SubscriptionStatus,
  type SubscriptionWritePayload,
} from '@/subscription-ui'
import { digitsOnly, formatVnd, trackerInvalidationKey, trackerQueryKey, type Tracker } from '@/tracker-ui'
import { errorMessage } from '@/tracker-undo'

const HIGHLIGHT_MS = 2000

function SubscriptionForm({
  initial,
  trackers,
  pending,
  onSubmit,
  onCancel,
}: {
  initial?: Subscription | null
  trackers: Tracker[]
  pending: boolean
  onSubmit: (payload: SubscriptionWritePayload) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [trackerId, setTrackerId] = useState(initial?.tracker_id ?? '')
  const [amount, setAmount] = useState(initial?.amount != null ? String(initial.amount) : '')
  const [listAmount, setListAmount] = useState(
    initial?.list_amount != null ? String(initial.list_amount) : '',
  )
  const [periodCount, setPeriodCount] = useState(String(initial?.period_count ?? 1))
  const [periodUnit, setPeriodUnit] = useState<PeriodUnit>(initial?.period_unit ?? 'month')
  const [startedOn, setStartedOn] = useState(initial?.started_on ?? '')
  const [expiresOn, setExpiresOn] = useState(initial?.expires_on ?? '')
  const [autoRenew, setAutoRenew] = useState(initial?.auto_renew ?? false)
  const [note, setNote] = useState(initial?.note_md ?? '')

  const count = Number(periodCount)
  const echoAmount = amount ? Number(digitsOnly(amount)) : null
  const canSubmit =
    !pending &&
    name.trim().length > 0 &&
    trackerId !== '' &&
    amount.length > 0 &&
    Number.isInteger(count) &&
    count > 0 &&
    startedOn !== '' &&
    expiresOn !== '' &&
    expiresOn >= startedOn

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit || echoAmount == null) return
    onSubmit({
      name: name.trim(),
      tracker_id: trackerId,
      amount: echoAmount,
      list_amount: listAmount ? Number(digitsOnly(listAmount)) : null,
      period_count: count,
      period_unit: periodUnit,
      started_on: startedOn,
      expires_on: expiresOn,
      auto_renew: autoRenew,
      note_md: note.trim() || null,
    })
  }

  return (
    <form data-testid="subscription-form" className="space-y-4" onSubmit={submit}>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tên đăng ký</span>
        <Input
          className="h-10 bg-card"
          value={name}
          maxLength={150}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tracker tài chính</span>
        <Select value={trackerId} onValueChange={setTrackerId}>
          <SelectTrigger className="w-full bg-card">
            <SelectValue placeholder="Chọn tracker" />
          </SelectTrigger>
          <SelectContent>
            {trackers.map((tracker) => (
              <SelectItem key={tracker.id} value={tracker.id}>
                {tracker.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Số tiền</span>
          <Input
            className="h-10 bg-card"
            inputMode="numeric"
            value={amount}
            onChange={(event) => setAmount(digitsOnly(event.target.value))}
          />
        </label>
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Giá niêm yết (nếu có)</span>
          <Input
            className="h-10 bg-card"
            inputMode="numeric"
            value={listAmount}
            onChange={(event) => setListAmount(digitsOnly(event.target.value))}
          />
        </label>
      </div>
      {echoAmount != null ? (
        <p className="text-lg font-extrabold text-primary tabular-nums">
          = {formatVnd(echoAmount)}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Chu kỳ</span>
          <Select value={periodUnit} onValueChange={(value) => setPeriodUnit(value as PeriodUnit)}>
            <SelectTrigger className="w-full bg-card">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="day">Ngày</SelectItem>
              <SelectItem value="week">Tuần</SelectItem>
              <SelectItem value="month">Tháng</SelectItem>
              <SelectItem value="year">Năm</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Số kỳ</span>
          <Input
            className="h-10 bg-card"
            type="number"
            min={1}
            value={periodCount}
            onChange={(event) => setPeriodCount(event.target.value)}
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Bắt đầu</span>
          <Input
            className="h-10 bg-card"
            type="date"
            value={startedOn}
            onChange={(event) => setStartedOn(event.target.value)}
          />
        </label>
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Hết hạn</span>
          <Input
            className="h-10 bg-card"
            type="date"
            min={startedOn}
            value={expiresOn}
            onChange={(event) => setExpiresOn(event.target.value)}
          />
        </label>
      </div>

      <label
        className="flex min-h-11 items-center gap-3 text-sm font-semibold"
        data-testid="subscription-auto-renew-hit-area"
      >
        <Checkbox
          className="size-5 rounded-md"
          checked={autoRenew}
          onCheckedChange={(checked) => setAutoRenew(checked === true)}
        />
        <span>Tự gia hạn (tính vào chi phí cố định)</span>
      </label>

      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Ghi chú</span>
        <Textarea
          className="min-h-24 bg-card font-normal"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>

      <div className="flex flex-wrap gap-2 pt-1">
        <Button size="lg" className="min-h-11" type="submit" disabled={!canSubmit}>
          {pending ? 'Đang lưu…' : initial ? 'Lưu thay đổi' : 'Tạo đăng ký'}
        </Button>
        <Button size="lg" variant="outline" className="min-h-11" type="button" onClick={onCancel}>
          Huỷ
        </Button>
      </div>
    </form>
  )
}

function RenewDialog({
  subscription,
  pending,
  onClose,
  onSubmit,
}: {
  subscription: Subscription
  pending: boolean
  onClose: () => void
  onSubmit: (payload: RenewPayload) => void
}) {
  const [amount, setAmount] = useState(subscription.amount != null ? String(subscription.amount) : '')
  const [occurredAt, setOccurredAt] = useState(toVietnamDateTimeInput(new Date().toISOString()))
  // F1: a LAPSED subscription resumes from today (§4.2 veto #8) — anchoring the
  // default to the stale expires_on would preview a new expiry in the past.
  const [newExpiresOn, setNewExpiresOn] = useState(() =>
    addPeriod(
      subscription.expires_on > todayVn() ? subscription.expires_on : todayVn(),
      subscription.period_count,
      subscription.period_unit,
      Number(subscription.started_on.slice(8, 10)),
    ),
  )
  const [expiryEdited, setExpiryEdited] = useState(false)
  const [note, setNote] = useState('')
  // §5.3: the entry_id is born once when the dialog opens and survives network
  // retries — generating a new id on retry would break the idempotency key.
  const entryIdRef = useRef<string | null>(null)
  if (entryIdRef.current === null) entryIdRef.current = uuidv7()

  const amountValue = amount ? Number(digitsOnly(amount)) : null
  const canSubmit =
    !pending && amountValue != null && amountValue > 0 && occurredAt !== '' && newExpiresOn !== ''

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit || amountValue == null) return
    onSubmit({
      entry_id: entryIdRef.current as string,
      amount: amountValue,
      occurred_at: vietnamInputToIso(occurredAt),
      // Send the date only when the owner actually changed it; an untouched
      // default must stay on the server's veto max(expires_on, today) so the
      // client clock can never race the server into a stale expiry (F1).
      ...(expiryEdited ? { new_expires_on: newExpiresOn } : {}),
      note_md: note.trim() || undefined,
    })
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !pending && onClose()}>
      <DialogContent data-testid="subscription-renew-dialog">
        <DialogHeader>
          <DialogTitle>Ghi gia hạn</DialogTitle>
          <DialogDescription>
            Ghi một khoản trả tiền thật và dời hạn cho “{subscription.name}”.
          </DialogDescription>
        </DialogHeader>
        <form data-testid="subscription-renew-form" className="space-y-4" onSubmit={submit}>
          <label className="block space-y-1.5 text-sm font-semibold">
            <span>Số tiền</span>
            <Input
              className="h-10 bg-card"
              inputMode="numeric"
              value={amount}
              onChange={(event) => setAmount(digitsOnly(event.target.value))}
            />
          </label>
          {amountValue != null ? (
            <p className="text-lg font-extrabold text-primary tabular-nums">
              = {formatVnd(amountValue)}
            </p>
          ) : null}
          <label className="block space-y-1.5 text-sm font-semibold">
            <span>Ngày trả</span>
            <Input
              className="h-10 bg-card"
              type="datetime-local"
              value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)}
            />
          </label>
          <label className="block space-y-1.5 text-sm font-semibold">
            <span>Hết hạn mới</span>
            <Input
              className="h-10 bg-card"
              type="date"
              value={newExpiresOn}
              onChange={(event) => {
                setNewExpiresOn(event.target.value)
                setExpiryEdited(true)
              }}
            />
          </label>
          <label className="block space-y-1.5 text-sm font-semibold">
            <span>Ghi chú</span>
            <Textarea
              className="min-h-24 bg-card font-normal"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <p
            data-testid="subscription-renew-summary"
            className="rounded-lg bg-muted/50 p-3 text-sm font-semibold"
          >
            {renewSummary(subscription.name, amountValue, newExpiresOn)}
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button size="lg" className="min-h-11" type="submit" disabled={!canSubmit}>
              {pending ? 'Đang ghi…' : 'Ghi gia hạn'}
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="min-h-11"
              type="button"
              disabled={pending}
              onClick={onClose}
            >
              Huỷ
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function SubscriptionCard({
  subscription,
  trackers,
  showListPrice,
  highlighted,
  onEdit,
  onRenew,
  onCancel,
  onUncancel,
  onDelete,
  pending,
}: {
  subscription: Subscription
  trackers: Tracker[]
  showListPrice: boolean
  highlighted: boolean
  onEdit: () => void
  onRenew: () => void
  onCancel: () => void
  onUncancel: () => void
  onDelete: () => void
  pending: boolean
}) {
  const trackerName = trackers.find((tracker) => tracker.id === subscription.tracker_id)?.name
  const showList =
    showListPrice &&
    subscription.list_amount != null &&
    subscription.list_amount !== subscription.amount
  return (
    <Card
      data-testid="subscription-card"
      data-subscription-id={subscription.id}
      data-highlighted={highlighted ? 'true' : 'false'}
      className={`gap-3 p-4 shadow-1 ring-0 transition-shadow ${highlighted ? 'ring-2 ring-primary' : ''}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <p className="max-w-full break-words text-sm font-bold">{subscription.name}</p>
          <p className="text-xs text-muted-foreground">
            {trackerName ?? 'Đã archive'}
            {subscription.auto_renew ? ' · tự gia hạn' : ''}
          </p>
        </div>
        <Badge
          data-testid="subscription-status"
          data-subscription-id={subscription.id}
          variant={
            subscription.status === 'active'
              ? 'secondary'
              : subscription.status === 'canceled'
                ? 'outline'
                : 'destructive'
          }
        >
          {statusLabel(subscription.status)}
        </Badge>
      </div>
      <div className="space-y-0.5">
        <p className="text-sm font-semibold tabular-nums">
          {subscription.corrupted ? (
            <span className="text-warn">không đọc được</span>
          ) : (
            <>
              {subscription.amount != null ? formatVnd(subscription.amount) : ''}{' '}
              <span className="font-normal text-muted-foreground">
                / {periodLabel(subscription.period_count, subscription.period_unit)}
              </span>
            </>
          )}
          {showList ? (
            <span className="ml-2 text-xs text-muted-foreground line-through">
              {formatVnd(subscription.list_amount as number)}
            </span>
          ) : null}
        </p>
        {subscription.monthly_amount != null ? (
          <p className="text-xs text-muted-foreground tabular-nums">
            ≈ {formatVnd(subscription.monthly_amount)}/tháng
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground tabular-nums">
          {formatShortDate(subscription.expires_on)} · {daysLeftLabel(subscription.days_left)}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          data-testid="subscription-renew"
          data-subscription-id={subscription.id}
          size="lg"
          className="min-h-11"
          disabled={pending}
          onClick={onRenew}
        >
          Ghi gia hạn
        </Button>
        {subscription.status === 'active' ? (
          <Button
            data-testid="subscription-cancel"
            data-subscription-id={subscription.id}
            size="lg"
            variant="outline"
            className="min-h-11"
            disabled={pending}
            onClick={onCancel}
          >
            Huỷ
          </Button>
        ) : null}
        {subscription.status === 'canceled' ? (
          <Button
            size="lg"
            variant="outline"
            className="min-h-11"
            disabled={pending}
            onClick={onUncancel}
          >
            Bỏ huỷ
          </Button>
        ) : null}
        <div className="ml-auto flex gap-2">
          <Button
            variant="ghost"
            size="icon-lg"
            className="size-11"
            aria-label={`Sửa ${subscription.name}`}
            disabled={pending}
            onClick={onEdit}
          >
            <Pencil />
          </Button>
          <Button
            variant="ghost"
            size="icon-lg"
            className="size-11"
            aria-label={`Xoá ${subscription.name}`}
            disabled={pending}
            onClick={onDelete}
          >
            <Trash2 />
          </Button>
        </div>
      </div>
    </Card>
  )
}

function SettingsBlock({
  items,
  pending,
  onToggleListPrice,
  onLeadDays,
}: {
  items: SettingsItem[]
  pending: boolean
  onToggleListPrice: (value: boolean) => void
  onLeadDays: (value: number) => void
}) {
  const showListPrice = items.find((item) => item.key === 'show_list_price')?.value !== false
  const storedLead = items.find((item) => item.key === 'subscription_expiry_lead_days')?.value
  // F8: the field is 0–30 (backend clamps to the same bounds). Never SHOW an
  // out-of-range value — a drifted server row or a typed 99 must not render as
  // a value the API would reject; the display (and the PATCH) stay in bounds.
  const clampLead = (value: number) => Math.min(30, Math.max(0, Math.round(value)))
  const [leadDays, setLeadDays] = useState(() =>
    typeof storedLead === 'number' ? clampLead(storedLead) : 3,
  )
  const lastStoredLead = useRef(storedLead)
  // Official "adjust state when props change" pattern: render-phase compare,
  // no effect, no cascading render.
  if (lastStoredLead.current !== storedLead) {
    lastStoredLead.current = storedLead
    if (typeof storedLead === 'number') setLeadDays(clampLead(storedLead))
  }

  function changeLeadDays(value: string) {
    if (value === '') {
      setLeadDays(0)
      return
    }
    const parsed = Number(value)
    if (!Number.isInteger(parsed)) return
    const clamped = clampLead(parsed)
    setLeadDays(clamped)
    onLeadDays(clamped)
  }

  return (
    <Card className="gap-3 p-4 shadow-1 ring-0">
      <h3 className="text-base font-bold">Cài đặt</h3>
      <label
        className="flex min-h-11 items-center gap-3 text-sm font-semibold"
        data-testid="settings-list-price-hit-area"
      >
        <Checkbox
          data-testid="settings-list-price-toggle"
          className="size-5 rounded-md"
          checked={showListPrice}
          disabled={pending}
          onCheckedChange={(checked) => onToggleListPrice(checked === true)}
        />
        <span>Hiện giá niêm yết gạch ngang</span>
      </label>
      <label className="flex flex-wrap items-center gap-3 text-sm font-semibold">
        <span>Nhắc trước khi hết hạn</span>
        <Input
          data-testid="settings-expiry-lead-days"
          className="h-10 w-24 bg-card"
          type="number"
          min={0}
          max={30}
          inputMode="numeric"
          value={leadDays}
          disabled={pending}
          onChange={(event) => changeLeadDays(event.target.value)}
        />
        <span className="text-xs font-normal text-muted-foreground">ngày (0–30)</span>
      </label>
    </Card>
  )
}

export function SubscriptionScreen() {
  const location = useLocation()
  const queryClient = useQueryClient()
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: subscriptionInvalidationKey })
    void queryClient.invalidateQueries({ queryKey: trackerInvalidationKey })
  }
  const writes = useSubscriptionWrites(refresh)

  const subscriptionsQuery = useQuery({
    queryKey: subscriptionQueryKey('subscriptions'),
    queryFn: () => apiRequest<{ items: Subscription[] }>('/api/subscriptions'),
    refetchInterval: standardRefetchInterval,
  })
  const settingsQuery = useQuery({
    queryKey: subscriptionQueryKey('settings'),
    queryFn: () => apiRequest<{ items: SettingsItem[] }>('/api/settings'),
    refetchInterval: standardRefetchInterval,
  })
  const trackersQuery = useQuery({
    queryKey: trackerQueryKey('trackers'),
    queryFn: () => apiRequest<{ items: Tracker[] }>('/api/tracker/trackers'),
    refetchInterval: standardRefetchInterval,
  })

  const subscriptions = useMemo(() => subscriptionsQuery.data?.items ?? [], [subscriptionsQuery.data])
  const trackers = useMemo(() => trackersQuery.data?.items ?? [], [trackersQuery.data])
  const settings = useMemo(() => settingsQuery.data?.items ?? [], [settingsQuery.data])

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<Subscription | null>(null)
  const [renewing, setRenewing] = useState<Subscription | null>(null)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const handledHighlight = useRef<string | null>(null)

  const highlightId = queryParams(location).get('highlight')
  useEffect(() => {
    if (!highlightId || handledHighlight.current === highlightId) return
    // F5: never interpolate a URL value into a selector string — a hostile
    // ``?highlight=`` is raw HTML/selector input. Trust only ids present in
    // the loaded list, then match by attribute comparison over the DOM.
    if (!subscriptions.some((subscription) => subscription.id === highlightId)) return
    const card = Array.from(
      document.querySelectorAll<HTMLElement>('[data-subscription-id]'),
    ).find((node) => node.getAttribute('data-subscription-id') === highlightId)
    if (!card) return
    handledHighlight.current = highlightId
    card.scrollIntoView({ behavior: 'smooth', block: 'center' })
    // Async so the ring class lands on the painted frame (no synchronous
    // setState inside the effect body).
    const showTimer = window.setTimeout(() => setHighlightedId(highlightId), 0)
    const clearTimer = window.setTimeout(() => setHighlightedId(null), HIGHLIGHT_MS)
    return () => {
      window.clearTimeout(showTimer)
      window.clearTimeout(clearTimer)
    }
  }, [highlightId, subscriptions])

  const groups = useMemo(() => {
    const order: SubscriptionStatus[] = ['active', 'canceled', 'expired']
    return order
      .map((status) => ({ status, items: subscriptions.filter((sub) => sub.status === status) }))
      .filter((group) => group.items.length > 0)
  }, [subscriptions])

  const queryError = subscriptionsQuery.error ?? settingsQuery.error

  function remove(subscription: Subscription) {
    writes.deleteSubscription.mutate(subscription.id, {
      onSuccess: () => {
        toast(<span>Đã xoá “{subscription.name}”</span>, {
          duration: 10_000,
          action: {
            label: 'Hoàn tác',
            onClick: () =>
              writes.restoreSubscription.mutate(subscription.id, {
                // F10: a failed restore must surface, not silently vanish.
                onError: (error) => toast.error(errorMessage(error)),
              }),
          },
        })
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const pending = [
    writes.createSubscription.isPending,
    writes.updateSubscription.isPending,
    writes.cancelSubscription.isPending,
    writes.uncancelSubscription.isPending,
    writes.renew.isPending,
    writes.deleteSubscription.isPending,
    writes.setSetting.isPending,
  ].some(Boolean)

  return (
    <div data-testid="subscription-screen" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Button
            size="icon-lg"
            variant="ghost"
            className="size-11 shrink-0"
            aria-label="Quay lại"
            // F6: an in-app entry is replaced so browser-Back cannot loop back
            // into /subscription; a cold-loaded screen keeps the spec's plain
            // navigate('/') so the initial entry is never eaten.
            onClick={() => navigate('/', { replace: hasAppHistory() })}
          >
            <ArrowLeft />
          </Button>
          <div className="min-w-0">
            <h2 className="text-lg font-extrabold text-primary">Đăng ký định kỳ</h2>
            <p className="text-sm text-muted-foreground">
              Khoản trả theo chu kỳ — ghi nhận việc gia hạn thật, không tự đoán.
            </p>
          </div>
        </div>
        <Button
          size="lg"
          className="min-h-11"
          onClick={() => {
            setEditing(null)
            setCreateOpen(true)
          }}
        >
          <Plus data-icon="inline-start" />
          Đăng ký mới
        </Button>
      </div>

      {queryError ? (
        <Card className="gap-3 p-4 shadow-1 ring-0" role="alert">
          <p className="text-sm text-bad">Không tải được dữ liệu đăng ký.</p>
          <Button variant="outline" size="lg" className="min-h-11" onClick={() => void refresh()}>
            <RefreshCw data-icon="inline-start" />
            Thử lại
          </Button>
        </Card>
      ) : null}

      {subscriptions.length === 0 && !subscriptionsQuery.isPending ? (
        <Card
          data-testid="subscription-empty"
          className="gap-3 p-4 shadow-1 ring-0"
        >
          <p className="text-sm text-muted-foreground">
            Chưa có đăng ký nào. Thêm khoản đầu tiên để theo dõi hạn và chi phí cố định.
          </p>
          <Button size="lg" className="min-h-11" onClick={() => setCreateOpen(true)}>
            <Plus data-icon="inline-start" />
            Tạo đăng ký
          </Button>
        </Card>
      ) : null}

      {groups.map((group) => (
        <div key={group.status} className="space-y-3">
          <h3 className="text-sm font-bold text-muted-foreground">{statusLabel(group.status)}</h3>
          {group.items.map((subscription) => (
            <SubscriptionCard
              key={subscription.id}
              subscription={subscription}
              trackers={trackers}
              showListPrice={
                settings.find((item) => item.key === 'show_list_price')?.value !== false
              }
              highlighted={highlightedId === subscription.id}
              pending={pending}
              onEdit={() => setEditing(subscription)}
              onRenew={() => setRenewing(subscription)}
              onCancel={() =>
                writes.cancelSubscription.mutate(subscription.id, {
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }
              onUncancel={() =>
                writes.uncancelSubscription.mutate(subscription.id, {
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }
              onDelete={() => remove(subscription)}
            />
          ))}
        </div>
      ))}

      <SettingsBlock
        items={settings}
        pending={writes.setSetting.isPending}
        onToggleListPrice={(value) =>
          writes.setSetting.mutate(
            { key: 'show_list_price', value },
            { onError: (error) => toast.error(errorMessage(error)) },
          )
        }
        onLeadDays={(value) =>
          writes.setSetting.mutate(
            { key: 'subscription_expiry_lead_days', value },
            { onError: (error) => toast.error(errorMessage(error)) },
          )
        }
      />

      <Dialog open={createOpen} onOpenChange={(open) => !open && setCreateOpen(false)}>
        <DialogContent data-testid="subscription-dialog">
          <DialogHeader>
            <DialogTitle>Đăng ký mới</DialogTitle>
            <DialogDescription>Tạo một khoản trả theo chu kỳ.</DialogDescription>
          </DialogHeader>
          <SubscriptionForm
            trackers={subscriptionTrackers(trackers)}
            pending={writes.createSubscription.isPending}
            onSubmit={(payload) =>
              writes.createSubscription.mutate(payload, {
                onSuccess: () => setCreateOpen(false),
                onError: (error) => toast.error(errorMessage(error)),
              })
            }
            onCancel={() => setCreateOpen(false)}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent data-testid="subscription-dialog">
          <DialogHeader>
            <DialogTitle>Sửa đăng ký</DialogTitle>
            <DialogDescription>Cập nhật thông tin của đăng ký này.</DialogDescription>
          </DialogHeader>
          {editing ? (
            <SubscriptionForm
              key={editing.id}
              initial={editing}
              trackers={subscriptionTrackers(trackers)}
              pending={writes.updateSubscription.isPending}
              onSubmit={(payload) =>
                writes.updateSubscription.mutate(
                  { subscriptionId: editing.id, payload },
                  {
                    onSuccess: () => setEditing(null),
                    onError: (error) => toast.error(errorMessage(error)),
                  },
                )
              }
              onCancel={() => setEditing(null)}
            />
          ) : null}
        </DialogContent>
      </Dialog>

      {renewing ? (
        <RenewDialog
          key={renewing.id}
          subscription={renewing}
          pending={writes.renew.isPending}
          onClose={() => setRenewing(null)}
          onSubmit={(payload) =>
            writes.renew.mutate(
              { subscriptionId: renewing.id, payload },
              {
                onSuccess: () => {
                  setRenewing(null)
                  toast('Đã ghi gia hạn')
                },
                onError: (error) => toast.error(errorMessage(error)),
              },
            )
          }
        />
      ) : null}
    </div>
  )
}
