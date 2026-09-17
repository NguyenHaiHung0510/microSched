import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  Bot,
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  Gauge,
  MessagesSquare,
  Orbit,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { fetchCurrentMimiConversation } from '@/mimi-api'
import { MimiScreen } from '@/MimiScreen'
import { mimiRunLabel } from '@/mimi-presentation'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

type CenterSection = 'overview' | 'activity' | 'conversations' | 'settings'

const sections: Array<{ id: CenterSection; label: string; icon: typeof Gauge }> = [
  { id: 'overview', label: 'Tổng quan', icon: Gauge },
  { id: 'activity', label: 'Hoạt động', icon: Activity },
  { id: 'conversations', label: 'Hội thoại', icon: MessagesSquare },
  { id: 'settings', label: 'Cấu hình', icon: Settings2 },
]

function StatCard({
  title,
  value,
  description,
  icon: Icon,
}: {
  title: string
  value: string
  description: string
  icon: typeof Gauge
}) {
  return (
    <Card className="gap-3">
      <CardHeader className="gap-2">
        <div className="flex items-center justify-between gap-3">
          <CardDescription>{title}</CardDescription>
          <Icon className="size-5 text-primary" aria-hidden="true" />
        </div>
        <CardTitle className="text-lg">{value}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  )
}

export function MimiControlCenter({ onOpenTasks }: { onOpenTasks: () => void }) {
  const [section, setSection] = useState<CenterSection>('overview')
  const conversation = useQuery({
    queryKey: ['mimi', 'current'],
    queryFn: fetchCurrentMimiConversation,
    ...NO_POLLING_QUERY_OPTIONS,
  })
  const current = conversation.data
  const latestRun = current?.runs.at(-1)
  const pendingApprovals = current?.change_sets.filter((item) => item.state === 'pending').length ?? 0
  const unresolvedFeedback = current?.feedback.filter((item) => item.unresolved).length ?? 0

  return (
    <section className="space-y-5" aria-labelledby="mimi-control-title">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Bot className="size-6 text-primary" aria-hidden="true" />
            <h2 id="mimi-control-title" className="text-2xl font-extrabold text-primary">
              Mimi Control Center
            </h2>
          </div>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Quản lý trạng thái, hoạt động, hội thoại và cấu hình đang thực sự có hiệu lực.
          </p>
        </div>
        <Badge variant="outline">P1R · local preview</Badge>
      </div>

      <nav className="flex gap-2 overflow-x-auto pb-1" aria-label="Khu quản lý Mimi">
        {sections.map(({ id, label, icon: Icon }) => (
          <Button
            key={id}
            size="lg"
            variant={section === id ? 'selected' : 'ghost'}
            aria-current={section === id ? 'page' : undefined}
            onClick={() => setSection(id)}
          >
            <Icon aria-hidden="true" />
            {label}
          </Button>
        ))}
      </nav>

      {section === 'overview' ? (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              title="Trạng thái Mimi"
              value={conversation.isError ? 'Cần kết nối lại' : 'Local dogfood'}
              description="Production vẫn tắt. Preview này không thay route-card hoặc Owner acceptance."
              icon={conversation.isError ? CircleAlert : CheckCircle2}
            />
            <StatCard
              title="Route hiệu lực"
              value="Chưa đủ route-card"
              description="Model/provider thật sẽ do backend công bố; không dùng nhãn hard-code trong UI."
              icon={BrainCircuit}
            />
            <StatCard
              title="Chờ Owner"
              value={`${pendingApprovals} preview`}
              description={`${unresolvedFeedback} feedback còn mở · mọi ghi Task vẫn cần xác nhận.`}
              icon={ShieldCheck}
            />
            <StatCard
              title="Run gần nhất"
              value={latestRun ? mimiRunLabel(latestRun.state) : 'Chưa có'}
              description="Activity giữ timing, route, usage và terminal state; transcript không gánh diagnostics."
              icon={Activity}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)]">
            <Card>
              <CardHeader>
                <CardTitle>Khả năng đang có</CardTitle>
                <CardDescription>Chỉ hiển thị capability thật, không dựng tab rỗng.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                {[
                  ['Đọc Task STANDARD', 'Có provenance và source version'],
                  ['Tạo Task có preview', 'Frozen digest · confirm/reject'],
                  ['Receipt và feedback', 'Durable, gắn đúng operation'],
                  ['Side-chat toàn app', 'Đang ở preview gate Task 058'],
                ].map(([title, detail]) => (
                  <div key={title} className="rounded-lg bg-muted/60 p-3">
                    <p className="font-semibold">{title}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Bước tiếp theo</CardTitle>
                <CardDescription>Capability-gated roadmap</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-start gap-3">
                  <Orbit className="mt-0.5 size-5 text-muted-foreground" aria-hidden="true" />
                  <div><p className="font-semibold">Orbit</p><p className="text-muted-foreground">Chưa bật · cần jobs/report thật.</p></div>
                </div>
                <div className="flex items-start gap-3">
                  <BrainCircuit className="mt-0.5 size-5 text-muted-foreground" aria-hidden="true" />
                  <div><p className="font-semibold">Memory & Skills</p><p className="text-muted-foreground">Không xuất hiện như module hoạt động trước capability.</p></div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}

      {section === 'activity' ? (
        <Card>
          <CardHeader>
            <CardTitle>Runs, receipts và diagnostics</CardTitle>
            <CardDescription>Thông tin vận hành tách khỏi transcript hội thoại.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!current?.runs.length ? <p className="text-sm text-muted-foreground">Chưa có run nào trong conversation hiện tại.</p> : null}
            {current?.runs.slice(-8).reverse().map((run) => (
              <article key={run.id} className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="font-semibold">Run {run.generation}</p>
                  <p className="truncate text-xs text-muted-foreground">{run.id}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{mimiRunLabel(run.state)}</Badge>
                  <Badge variant="secondary">{run.provider_outcome === 'succeeded' ? 'Provider hoàn tất' : run.provider_outcome === 'failed' ? 'Provider lỗi' : 'Chưa có kết quả provider'}</Badge>
                </div>
              </article>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {section === 'conversations' ? (
        <div className="grid min-w-0 gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
          <Card className="content-start">
            <CardHeader>
              <CardTitle>Hội thoại</CardTitle>
              <CardDescription>New/switch/rename/archive được nối ở 058B.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button className="w-full justify-start" variant="selected">
                <MessagesSquare aria-hidden="true" /> Conversation hiện tại
              </Button>
              <Button className="w-full justify-start" variant="outline" disabled>
                <Bot aria-hidden="true" /> Hội thoại mới · chờ 058B
              </Button>
            </CardContent>
          </Card>
          <Card className="min-w-0">
            <CardContent className="p-4 sm:p-5">
              <MimiScreen onOpenTasks={onOpenTasks} variant="workspace" />
            </CardContent>
          </Card>
        </div>
      ) : null}

      {section === 'settings' ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2"><SlidersHorizontal className="size-5 text-primary" aria-hidden="true" /><CardTitle>Interactive runtime</CardTitle></div>
              <CardDescription>Requested và effective phải tách biệt.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3"><span>Requested ceiling</span><Badge>7 phút</Badge></div>
              <div className="flex items-center justify-between gap-3"><span>Effective P1 client</span><Badge variant="destructive">20 giây · cần sửa</Badge></div>
              <div className="flex items-center justify-between gap-3"><span>Streaming</span><Badge variant="outline">Đã duyệt · chưa effective</Badge></div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Provider policy</CardTitle>
              <CardDescription>Không hiển thị hoặc chỉnh API key trong client.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3"><span>Evaluation</span><Badge variant="outline">Exact pin</Badge></div>
              <div className="flex items-center justify-between gap-3"><span>Dogfood</span><Badge variant="outline">Eligible pool</Badge></div>
              <div className="flex items-center justify-between gap-3"><span>Privacy</span><Badge variant="secondary">ZDR + data deny</Badge></div>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </section>
  )
}
