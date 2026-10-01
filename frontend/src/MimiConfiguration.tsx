import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'

import { ApiError } from '@/api'
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
              <p className="text-xs font-semibold">{profile.available ? 'Khả dụng' : 'Chưa khả dụng'}</p>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {profile.provider} · {profile.quantization || 'Quantization không được cung cấp'} · Effort: {profile.supported_efforts.length ? profile.supported_efforts.join(', ') : 'Theo model'}
            </p>
            <p className="text-xs text-muted-foreground">
              Tổng context model: {profile.context_limit.toLocaleString('vi-VN')} token · dành {profile.output_reserve.toLocaleString('vi-VN')} token cho câu trả lời
            </p>
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
}: {
  conversationId: string
  capabilities: MimiCapabilities | undefined
  runtimeActive: boolean
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

  const activeRunId = configuration.data?.active_run_id
  const profiles = configuration.data?.profiles.length
    ? configuration.data.profiles
    : capabilities?.model_profiles ?? []

  return (
    <details className="shrink-0 rounded-xl border bg-card px-3 py-2" data-testid="mimi-route-settings">
      <summary className="cursor-pointer py-1 text-sm font-semibold">
        Cấu hình Mimi
        <span className="ml-2 font-normal text-muted-foreground">
          {selectedProfile?.label ?? (capabilities?.live_provider_enabled ? 'Theo server' : 'Chế độ local')}
        </span>
        {enabled && (activeRunId || runtimeActive) ? (
          <span className="ml-2 font-normal text-muted-foreground" role="status" data-testid="mimi-next-run-notice">
            Run đang hoạt động · cấu hình mới áp dụng từ lượt sau
          </span>
        ) : null}
      </summary>

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
          <div className="grid gap-3 sm:grid-cols-3">
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
                  {configuration.data?.profiles.map((profile) => (
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
              <label htmlFor={`mimi-context-${conversationId}`} className="text-sm font-semibold">Ngân sách đầu vào</label>
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
          </div>

          <p className="text-xs text-muted-foreground">
            Tổng context của lượt: {(selection.input_tokens + (selectedProfile?.output_reserve ?? 0)).toLocaleString('vi-VN')} token, gồm ngân sách đầu vào và output reserve {selectedProfile?.output_reserve.toLocaleString('vi-VN') ?? '—'} token; giới hạn model là {selectedProfile?.context_limit.toLocaleString('vi-VN') ?? '—'} token. Lưu cấu hình chỉ áp dụng từ lượt chạy tiếp theo
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
            disabled={!dirty || save.isPending || !selectedProfile?.available || !efforts.includes(selection.effort) || !presets.includes(selection.input_tokens)}
            onClick={() => configuration.data && save.mutate({ next: selection, expectedVersion: configuration.data.version })}
          >
            {save.isPending ? 'Đang lưu…' : 'Lưu lựa chọn'}
          </Button>
        </div>
      ) : null}
    </details>
  )
}
