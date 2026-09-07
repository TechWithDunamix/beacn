/** BEACN-observed tasks. Celery is one producer; the UI is producer-agnostic. */

import { Head, router } from '@inertiajs/react'
import { ago, dateTime, latency } from '@/js/hooks'
import { Badge, Empty, PageHeader, Table, TBody, TD, TH, THead, TR } from '@/views/ui/kit'

interface Task {
  id: string
  task_id: string
  name: string | null
  topic: string
  producer: string | null
  status: string
  progress: number | null
  attempts: number
  duration_ms: number | null
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  correlation_id: string | null
}

const TONE: Record<string, 'neutral' | 'brand' | 'ok' | 'caution' | 'critical'> = {
  created: 'neutral',
  started: 'brand',
  retrying: 'caution',
  completed: 'ok',
  failed: 'critical',
  revoked: 'neutral',
}
const FILTERS = ['', 'started', 'retrying', 'completed', 'failed', 'revoked']

export default function Tasks({ environment, status, tasks }: { environment: string; status: string | null; tasks: Task[] }) {
  return (
    <>
      <Head title="Tasks" />
      <PageHeader
        title="Tasks"
        subtitle={`${environment} · BEACN-observed from task.* events`}
        actions={
          <div className="flex gap-1">
            {FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => router.get('/tasks', { env: environment, ...(f ? { status: f } : {}) })}
                className={`rounded-full px-3 py-1 text-[12px] font-medium ${
                  (status ?? '') === f ? 'bg-primary text-on-primary' : 'text-ink-muted hover:bg-sunken'
                }`}
              >
                {f || 'all'}
              </button>
            ))}
          </div>
        }
      />

      {tasks.length === 0 ? (
        <Empty
          title="No tasks"
          body="A producer emitting task.created / task.started / task.completed events populates this. Wire up integrations/celery.py in a worker, or publish the events directly."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Task</TH>
              <TH>Producer</TH>
              <TH>Status</TH>
              <TH align="right">Attempts</TH>
              <TH align="right">Duration</TH>
              <TH align="right">Updated</TH>
            </TR>
          </THead>
          <TBody>
            {tasks.map((t) => (
              <TR key={t.id}>
                <TD>
                  <div className="font-medium text-ink">{t.name ?? '(unnamed)'}</div>
                  <div className="mono text-[11px] text-ink-faint">{t.task_id}</div>
                  {t.error && <div className="mt-1 text-[11px] text-critical">{t.error.slice(0, 140)}</div>}
                </TD>
                <TD>{t.producer ?? '—'}</TD>
                <TD>
                  <Badge tone={TONE[t.status] ?? 'neutral'} dot>{t.status}</Badge>
                  {t.progress != null && (
                    <span className="ml-2 num text-[11px] text-ink-faint">{Math.round(t.progress * 100)}%</span>
                  )}
                </TD>
                <TD align="right">{t.attempts}</TD>
                <TD align="right">{latency(t.duration_ms)}</TD>
                <TD align="right" title={dateTime(t.finished_at ?? t.started_at ?? t.created_at)}>
                  {ago(t.finished_at ?? t.started_at ?? t.created_at)}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </>
  )
}
