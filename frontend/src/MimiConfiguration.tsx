import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ApiError } from '@/api'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { availableInputPresets, effortOptions } from '@/mimi-configuration'
import {
  fetchMimiConfiguration,
  type MimiCapabilities,
  type MimiConversationConfiguration,
  type MimiModelProfile,
  type MimiRouteConfig,
  saveMimiConfiguration,
  refreshMimiProviderPool,
} from '@/mimi-api'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

function ModelProfileDetails({ profiles }: { profiles: MimiModelProfile[] }) {
  if (profiles.length === 0) return null

  return (
    <details className="rounded-lg border px-3 py-2" data-testid="mimi-profile-details">
      <summary className="cursor-pointer py-1 text-sm font-semibold">
        Thông tin tuyến model ({profiles.length})
      </summary>
      <ul className="mt-2 space-y-2">
        {profiles.map((profile) => (
          <li key={profile.id} className="rounded-lg bg-muted/50 p-3 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <p className="font-semibold">{profile.label} · {profile.model}</p>
              <p className="text-xs font-semibold">{profile.available ? 'Được phép chọn' : 'Chưa khả dụng'}</p>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {profile.provider} · {profile.quantization || 'Quantization không được cung cấp'} · Effort: {profile.supported_efforts.length ? profile.supported_efforts.join(', ') : 'Theo model'}
            </p>
            <p className="text-xs text-muted-foreground">
              Tổng context model: {profile.context_limit.toLocaleString('vi-VN')} token · dành {profile.output_reserve.toLocaleString('vi-VN')} token cho câu trả lời
            </p>
            {profile.evidence ? <p className="mt-1 text-xs text-muted-foreground">Bằng chứng route: {profile.evidence}</p> : null}
            {!profile.available && profile.unavailable_reason ? (
              <p className="mt-1 text-xs">Lý do: {profile.unavailable_reason}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  )
}

function configurationError(error: unknown) {
  if (error instanceof ApiError && error.status === 409) {
    return 'Cấu hình đã đổi trên server. Lựa chọn của bạn vẫn được giữ; tải cấu hình mới rồi lưu lại.'
  }
  return 'Chưa lưu được cấu hình. Lựa chọn của bạn vẫn được giữ để thử lại.'
}

export function MimiConfiguration({
  conversationId,
  capabilities,
  runtimeActive,
  open,
  onOpenChange,
}: {
  conversationId: string
  capabilities: MimiCapabilities | undefined
  runtimeActive: boolean
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const enabled = capabilities?.model_selection_enabled === true
  const queryClient = useQueryClient()
  const queryKey = ['mimi', 'configuration', conversationId]
  const configuration = useQuery({
    queryKey,
    queryFn: () => fetchMimiConfiguration(conversationId),
    enabled,
    ...NO_POLLING_QUERY_OPTIONS,
  })
  const previousRuntimeActive = useRef(runtimeActive)
  const [localSelection, setSelection] = useState<MimiRouteConfig | null>(null)
  const [dirty, setDirty] = useState(false)
  const selection = localSelection ?? configuration.data?.config ?? null
  const refetchConfiguration = configuration.refetch

  useEffect(() => {
    const runStateChanged = previousRuntimeActive.current !== runtimeActive
    previousRuntimeActive.current = runtimeActive
    if (enabled && runStateChanged) void refetchConfiguration()
  }, [enabled, runtimeActive, conversationId, refetchConfiguration])

  const selectedProfile = useMemo(
    () => configuration.data?.profiles.find((profile) => profile.id === selection?.profile_id),
    [configuration.data?.profiles, selection?.profile_id],
  )
  const presets = availableInputPresets(selectedProfile)
  const efforts = effortOptions(selectedProfile)
  const hasCurrentPreset = selection ? presets.includes(selection.input_tokens) : false
  const hasCurrentEffort = selection ? efforts.includes(selection.effort) : false

  const save = useMutation({
    mutationFn: ({ next, expectedVersion }: { next: MimiRouteConfig; expectedVersion: number }) =>
      saveMimiConfiguration(conversationId, next, expectedVersion),
    onSuccess: (saved) => {
      queryClient.setQueryData<MimiConversationConfiguration>(queryKey, saved)
      setSelection(null)
      setDirty(false)
    },
  })

  function updateSelection(next: MimiRouteConfig) {
    setSelection(next)
    setDirty(true)
    save.reset()
  }

  const refreshPool = useMutation({ mutationFn: () => refreshMimiProviderPool(conversationId) })
  const activeRunId = configuration.data?.active_run_id
  const profiles = configuration.data?.profiles.length
    ? configuration.data.profiles
    : capabilities?.model_profiles ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogTrigger asChild><Button type="button" size="sm" variant="ghost" className="mimi-model-chip mb-1 max-w-full justify-start gap-1.5 text-xs" data-testid="mimi-route-settings" aria-label="Cấu hình model và effort"><SlidersHorizontal className="size-3.5" /><span className="truncate">{selectedProfile?.label ?? 'Model theo server'} · {selection?.effort ?? capabilities?.requested_effort ?? 'chưa rõ'}</span><ChevronDown className="size-3" /></Button></DialogTrigger><DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl"><DialogHeader><DialogTitle>Cấu hình Mimi</DialogTitle><DialogDescription>Áp dụng cho lượt chạy tiếp theo; giữ đúng model và effort đã chọn.</DialogDescription></DialogHeader>{enabled && (activeRunId || runtimeActive) ? <p role="status" className="text-xs" data-testid="mimi-next-run-notice">Run đang hoạt động · cấu hình mới áp dụng từ lượt sau</p> : null}

      {!enabled ? (
        <div className="space-y-3 pb-2 pt-1">
          <p className="text-sm text-muted-foreground">
            {capabilities?.live_provider_enabled
              ? 'Server đang chọn model cho lượt chat này.'
              : 'Lượt chat này chưa dùng model bên ngoài.'}
          </p>
          <ModelProfileDetails profiles={profiles} />
        </div>
      ) : configuration.isPending ? (
        <p role="status" className="pb-2 pt-1 text-sm text-muted-foreground">Đang tải lựa chọn model…</p>
      ) : configuration.isError && !configuration.data ? (
        <div className="space-y-2 pb-2 pt-1">
          <p role="alert" className="text-sm text-bad">Không tải được cấu hình. Thử tải lại trước khi đổi model.</p>
          <Button type="button" size="lg" variant="outline" onClick={() => void configuration.refetch()}>Tải lại</Button>
        </div>
      ) : selection ? (
        <div className="space-y-3 pb-2 pt-2">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="min-w-0 space-y-1.5">
              <label htmlFor={`mimi-profile-${conversationId}`} className="text-sm font-semibold">Model</label>
              <Select
                value={selection.profile_id}
                disabled={save.isPending}
                onValueChange={(profileId) => {
                  const profile = configuration.data?.profiles.find((item) => item.id === profileId)
                  if (!profile) return
                  const nextEfforts = effortOptions(profile)
                  const nextPresets = availableInputPresets(profile)
                  updateSelection({
                    ...selection,
                    profile_id: profile.id,
                    effort: nextEfforts.includes(selection.effort) ? selection.effort : nextEfforts[0],
                    input_tokens: nextPresets.includes(selection.input_tokens)
                      ? selection.input_tokens
                      : nextPresets.at(-1) ?? selection.input_tokens,
                  })
                }}
              >
                <SelectTrigger id={`mimi-profile-${conversationId}`} className="min-h-11 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {configuration.data?.profiles.filter((profile) => profile.id === 'deepseek').map((profile) => (
                    <SelectItem key={profile.id} value={profile.id} disabled={!profile.available}>
                      {profile.label} · {profile.model}{!profile.available && profile.unavailable_reason ? ` · ${profile.unavailable_reason}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="min-w-0 space-y-1.5">
              <label htmlFor={`mimi-effort-${conversationId}`} className="text-sm font-semibold">Mức suy luận</label>
              <Select
                value={selection.effort}
                disabled={save.isPending || !selectedProfile?.available}
                onValueChange={(effort) => updateSelection({ ...selection, effort })}
              >
                <SelectTrigger id={`mimi-effort-${conversationId}`} className="min-h-11 w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {efforts.map((effort) => (
                    <SelectItem key={effort} value={effort}>{effort === 'default' ? 'Theo model' : effort}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="min-w-0 space-y-1.5">
              <label htmlFor={`mimi-context-${conversationId}`} className="text-sm font-semibold">Ngưỡng compact quan sát</label>
              <Select
                value={String(selection.input_tokens)}
                disabled={save.isPending || !selectedProfile?.available || presets.length === 0}
                onValueChange={(tokens) => updateSelection({ ...selection, input_tokens: Number(tokens) })}
              >
                <SelectTrigger id={`mimi-context-${conversationId}`} className="min-h-11 w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {presets.map((tokens) => (
                    <SelectItem key={tokens} value={String(tokens)}>{tokens.toLocaleString('vi-VN')} token</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-0 space-y-1.5"><label htmlFor={`mimi-window-budget-${conversationId}`} className="text-sm font-semibold">Cửa sổ ngữ cảnh / ngân sách input</label><Select value="profile" disabled><SelectTrigger id={`mimi-window-budget-${conversationId}`} className="min-h-11 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="profile">{selectedProfile ? `${(selectedProfile.context_limit - selectedProfile.output_reserve).toLocaleString('vi-VN')} token input` : 'Theo profile server'}</SelectItem></SelectContent></Select><p className="text-xs text-muted-foreground">Tổng cửa sổ {selectedProfile?.context_limit.toLocaleString('vi-VN') ?? '—'} token, dành {selectedProfile?.output_reserve.toLocaleString('vi-VN') ?? '—'} token output. Profile hiện tại chốt cửa sổ; chưa hỗ trợ đổi riêng ngân sách input.</p></div>
          </div>

          <fieldset className="space-y-3 rounded-lg border p-3"><legend className="px-1 text-xs font-semibold">Provider của đúng model / effort đã chọn</legend><div className="grid gap-3 sm:grid-cols-3"><div><label className="text-xs font-semibold" htmlFor={`mimi-routing-${conversationId}`}>Chính sách</label><Select value={selection.routing_mode ?? 'adaptive'} onValueChange={(value) => updateSelection({ ...selection, routing_mode: value as 'exact' | 'adaptive' })}><SelectTrigger id={`mimi-routing-${conversationId}`}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="adaptive">Provider thích ứng</SelectItem><SelectItem value="exact">Provider đã cấu hình</SelectItem></SelectContent></Select></div><div><label className="text-xs font-semibold" htmlFor={`mimi-uptime-${conversationId}`}>Uptime phải lớn hơn (%)</label><Input id={`mimi-uptime-${conversationId}`} type="number" min={0} max={99.999} step={0.1} value={selection.min_uptime_percent ?? 95} onChange={(event) => updateSelection({ ...selection, min_uptime_percent: event.target.value === '' ? Number.NaN : Number(event.target.value) })} /></div><div><label className="text-xs font-semibold" htmlFor={`mimi-window-${conversationId}`}>Cửa sổ uptime</label><Select value={selection.uptime_window ?? '1d'} onValueChange={(value) => updateSelection({ ...selection, uptime_window: value as '1d' | '30m' })}><SelectTrigger id={`mimi-window-${conversationId}`}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="1d">1 ngày</SelectItem><SelectItem value="30m">30 phút</SelectItem></SelectContent></Select></div></div><p className="text-xs text-muted-foreground">Chỉ đổi provider đủ điều kiện về privacy, giá và uptime; giữ nguyên DeepSeek V4.1 Flash cùng effort. Không hạ privacy hoặc đổi model khi không có endpoint phù hợp.</p><Button type="button" size="sm" variant="outline" disabled={refreshPool.isPending || save.isPending || dirty} onClick={() => refreshPool.mutate()}>{refreshPool.isPending ? 'Đang đọc metadata…' : 'Làm mới pool đã lưu'}</Button>{refreshPool.isError ? <p role="alert" className="text-xs text-bad">Chưa đọc được pool đủ điều kiện. Không tự đổi model.</p> : null}{refreshPool.data ? <p className="break-words text-xs">{refreshPool.data.model} · {refreshPool.data.effort} · {refreshPool.data.tags.join(', ') || 'Không có endpoint'} · uptime &gt; {refreshPool.data.min_uptime_percent}% / {refreshPool.data.window} · lúc {new Date(refreshPool.data.checked_at * 1000).toLocaleString('vi-VN')}</p> : null}</fieldset>
          <p className="text-xs text-muted-foreground">
            Mimi compact ở lượt sau khi provider báo input main đạt {selection.input_tokens.toLocaleString('vi-VN')} token. Request có thể vượt ngưỡng này; giới hạn endpoint là {selectedProfile?.context_limit.toLocaleString('vi-VN') ?? '—'} token, output tối đa {selectedProfile?.output_reserve.toLocaleString('vi-VN') ?? '—'} token. Lưu cấu hình chỉ áp dụng từ lượt chạy tiếp theo
            {activeRunId || runtimeActive ? '; lượt đang chạy giữ nguyên lựa chọn đã chốt.' : '.'}
          </p>
          {!hasCurrentPreset ? <p role="alert" className="text-sm text-bad">Mức ngữ cảnh hiện tại không còn hợp lệ cho model này. Chọn mức được hỗ trợ để lưu.</p> : null}
          {!hasCurrentEffort ? <p role="alert" className="text-sm text-bad">Effort hiện tại không nằm trong các mức server quảng bá. Chọn mức khả dụng trước khi lưu.</p> : null}
          {save.isError ? (
            <div className="space-y-2" role="alert">
              <p className="text-sm text-bad">{configurationError(save.error)}</p>
              {save.error instanceof ApiError && save.error.status === 409 ? (
                <Button type="button" size="lg" variant="outline" disabled={configuration.isFetching} onClick={() => void configuration.refetch()}>
                  {configuration.isFetching ? 'Đang tải…' : 'Tải cấu hình mới'}
                </Button>
              ) : null}
            </div>
          ) : null}
          {save.isSuccess ? <p role="status" className="text-sm text-ok">Đã lưu cho lượt chạy tiếp theo.</p> : null}
          <ModelProfileDetails profiles={profiles} />
          <Button
            type="button"
            size="lg"
            disabled={!Number.isFinite(selection.min_uptime_percent ?? 95) || (selection.min_uptime_percent ?? 95) < 0 || (selection.min_uptime_percent ?? 95) >= 100 || !dirty || save.isPending || !selectedProfile?.available || !efforts.includes(selection.effort) || !presets.includes(selection.input_tokens)}
            onClick={() => configuration.data && save.mutate({ next: selection, expectedVersion: configuration.data.version })}
          >
            {save.isPending ? 'Đang lưu…' : 'Lưu lựa chọn'}
          </Button>
        </div>
      ) : null}
    </DialogContent></Dialog>
  )
}
