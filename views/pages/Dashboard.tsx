/**
 * The realtime infrastructure dashboard.
 *
 * Every figure comes from the durable store plus this instance's live realtime
 * counters. A fresh install shows zeros and empty states — nothing is invented.
 * The page polls `/api/control/dashboard` every 5s so the numbers move.
 */

import { Head, router } from '@inertiajs/react'
import { useEffect, useState } from 'react'
import { ago, compact, count, dateTime, percent } from '@/js/hooks'
import { api } from '@/js/api'
import {
  Badge,
  Empty,
  Panel,
  PanelHeader,
  Stat,
  StatRow,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from '@/views/ui/kit'
import { Sparkline } from '@/views/ui/Spark'

interface Summary {
  environment: string
  events: { per_second: number; last_minute: number; last_hour: number; today: number; total: number }
  delivery: { attempts_24h: number; delivered_24h: number; failed_24h: number; success_rate: number | null }
  realtime: {
    connections_open: number
    connections_this_instance: number
    subscriptions_this_instance: number
    frames_sent_this_instance: number
    events_dropped_this_instance: number
  }
  tasks: { running: number; failed_today: number }
  producers: { total: number; active: number }
  keys: { active: number }
  topics: number
}

interface Props {
  environment: string
  summary: Summary
  top_producers: { producer: string; events: number }[]
  top_topics: { topic: string; events: number }[]
  recent_events: {
    id: string
    event: string
    topic: string
    producer: string | null
    severity: string
    timestamp: string
  }[]
  throughput: { minute: string; count: number }[]
}

const SEV_TONE: Record<string, 'neutral' | 'brand' | 'caution' | 'critical'> = {
  debug: 'neutral',
  info: 'neutral',
  notice: 'brand',
  warning: 'caution',
  error: 'critical',
  critical: 'critical',
}

export default function Dashboard(initial: Props) {
  const [data, setData] = useState<Props>(initial)

  useEffect(() => {
    setData(initial)
  }, [initial])

  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const fresh = await api.get<{
          summary: Summary
          top_producers: Props['top_producers']
          top_topics: Props['top_topics']
          recent_events: Props['recent_events']
          throughput: Props['throughput']
        }>('/dashboard', { environment: initial.environment })
        setData((d) => ({ ...d, ...fresh }))
      } catch {
        // transient; the next tick tries again
      }
    }, 5000)
    return () => clearInterval(timer)
  }, [initial.environment])

  const s = data.summary
  const empty = s.events.total === 0

  return (
    <>
      <Head title="Dashboard" />
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.02em] text-ink">Dashboard</h1>
          <p className="mt-1 text-[13px] text-ink-muted">
            Event infrastructure for the <span className="font-medium text-ink">{data.environment}</span>{' '}
            environment.
          </p>
        </div>
        <button
          type="button"
          onClick={() => router.reload()}
          className="text-[12px] font-medium text-brand hover:underline"
        >
          Refresh
        </button>
      </div>

      <StatRow>
        <Stat label="Events / sec" value={s.events.per_second.toFixed(2)} hint={`${count(s.events.last_minute)} in the last minute`} />
        <Stat label="Events today" value={compact(s.events.today)} hint={`${count(s.events.total)} stored`} />
        <Stat
          label="Delivery success"
          value={s.delivery.success_rate === null ? '—' : percent(s.delivery.success_rate, 1)}
          hint={`${count(s.delivery.delivered_24h)} / ${count(s.delivery.attempts_24h)} in 24h`}
          tone={s.delivery.success_rate !== null && s.delivery.success_rate < 0.99 ? 'critical' : undefined}
        />
        <Stat
          label="Open connections"
          value={count(s.realtime.connections_open)}
          hint={`${count(s.realtime.subscriptions_this_instance)} subs on this node`}
        />
      </StatRow>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Panel className="lg:col-span-2" padded={false}>
          <PanelHeader title="Throughput" description="Events persisted per minute, last hour" />
          <div className="p-5">
            <Sparkline points={data.throughput.map((p) => p.count)} height={120} />
          </div>
        </Panel>
        <Panel padded={false}>
          <PanelHeader title="System" />
          <dl className="divide-y divide-line px-5">
            {[
              ['Active producers', `${s.producers.active} / ${s.producers.total}`],
              ['Active API keys', String(s.keys.active)],
              ['Topics', String(s.topics)],
              ['Tasks running', String(s.tasks.running)],
              ['Tasks failed today', String(s.tasks.failed_today)],
              ['Frames sent (node)', compact(s.realtime.frames_sent_this_instance)],
              ['Events dropped (node)', compact(s.realtime.events_dropped_this_instance)],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between py-2.5 text-[12px]">
                <dt className="text-ink-muted">{k}</dt>
                <dd className="font-medium text-ink num">{v}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel padded={false}>
          <PanelHeader title="Top producers" description="By event volume" />
          {data.top_producers.length === 0 ? (
            <Empty title="No producers yet" body="Register one and issue a key to start publishing." />
          ) : (
            <ul className="divide-y divide-line">
              {data.top_producers.map((p) => (
                <li key={p.producer} className="flex items-center justify-between px-5 py-2.5 text-[13px]">
                  <span className="text-ink">{p.producer}</span>
                  <span className="num text-ink-muted">{count(p.events)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel padded={false}>
          <PanelHeader title="Top topics" description="By event volume" />
          {data.top_topics.length === 0 ? (
            <Empty title="No topics yet" body="Topics appear as producers publish to them." />
          ) : (
            <ul className="divide-y divide-line">
              {data.top_topics.map((t) => (
                <li key={t.topic} className="flex items-center justify-between px-5 py-2.5 text-[13px]">
                  <span className="mono text-ink">{t.topic}</span>
                  <span className="num text-ink-muted">{count(t.events)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel className="mt-4" padded={false}>
        <PanelHeader title="Recent events" />
        {empty ? (
          <Empty
            title="No events yet"
            body="Publish to POST /api/v1/events with an API key, or send task.* events from a Celery worker."
          />
        ) : (
          <Table className="rounded-none border-0">
            <THead>
              <TR>
                <TH>Event</TH>
                <TH>Topic</TH>
                <TH>Producer</TH>
                <TH>Severity</TH>
                <TH align="right">When</TH>
              </TR>
            </THead>
            <TBody>
              {data.recent_events.map((e) => (
                <TR key={e.id} href={`/events/${e.id}`}>
                  <TD>
                    <a href={`/events/${e.id}`} className="font-medium text-ink hover:text-brand">
                      {e.event}
                    </a>
                    <div className="mono text-[11px] text-ink-faint">{e.id}</div>
                  </TD>
                  <TD><span className="mono">{e.topic}</span></TD>
                  <TD>{e.producer ?? '—'}</TD>
                  <TD><Badge tone={SEV_TONE[e.severity] ?? 'neutral'}>{e.severity}</Badge></TD>
                  <TD align="right" title={dateTime(e.timestamp)}>{ago(e.timestamp)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>
    </>
  )
}
