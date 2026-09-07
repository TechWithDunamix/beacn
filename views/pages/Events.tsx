/** Searchable event explorer with server-side cursor pagination. */

import { Head, router } from '@inertiajs/react'
import { useState } from 'react'
import { ago, dateTime } from '@/js/hooks'
import {
  Badge,
  Empty,
  Input,
  PageHeader,
  Select,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from '@/views/ui/kit'
import type { BeacnEvent } from '@/js/types'

interface Props {
  environment: string
  filters: {
    topic: string | null
    event_prefix: string | null
    kind: string | null
    severity: string | null
    producer_id: string | null
  }
  producers: { id: string; name: string }[]
  events: BeacnEvent[]
  page: { count: number; next_cursor: string | null; has_more: boolean }
}

const KINDS = ['', 'event', 'task', 'notification', 'message']
const SEVERITIES = ['', 'debug', 'info', 'notice', 'warning', 'error', 'critical']

export default function Events({ environment, filters, producers, events, page }: Props) {
  const [form, setForm] = useState({
    topic: filters.topic ?? '',
    event_prefix: filters.event_prefix ?? '',
    kind: filters.kind ?? '',
    severity: filters.severity ?? '',
    producer_id: filters.producer_id ?? '',
  })

  const apply = (extra: Record<string, string> = {}) => {
    const params: Record<string, string> = { env: environment }
    for (const [k, v] of Object.entries({ ...form, ...extra })) if (v) params[k] = v
    router.get('/events', params, { preserveState: true, preserveScroll: true })
  }

  return (
    <>
      <Head title="Events" />
      <PageHeader title="Events" subtitle={`${environment} · ${page.count} shown`} />

      <div className="surface mb-4 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
        <Input
          placeholder="Topic"
          value={form.topic}
          onChange={(e) => setForm({ ...form, topic: e.target.value })}
          onKeyDown={(e) => e.key === 'Enter' && apply()}
        />
        <Input
          placeholder="Event name prefix"
          value={form.event_prefix}
          onChange={(e) => setForm({ ...form, event_prefix: e.target.value })}
          onKeyDown={(e) => e.key === 'Enter' && apply()}
        />
        <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
          {KINDS.map((k) => (
            <option key={k} value={k}>{k || 'any kind'}</option>
          ))}
        </Select>
        <Select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s || 'any severity'}</option>
          ))}
        </Select>
        <Select value={form.producer_id} onChange={(e) => setForm({ ...form, producer_id: e.target.value })}>
          <option value="">any producer</option>
          {producers.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </Select>
        <div className="flex gap-2 sm:col-span-2 lg:col-span-5">
          <button
            type="button"
            onClick={() => apply()}
            className="rounded-full bg-primary px-4 py-1.5 text-[12px] font-medium text-on-primary hover:bg-primary-hover"
          >
            Apply
          </button>
          <button
            type="button"
            onClick={() => {
              setForm({ topic: '', event_prefix: '', kind: '', severity: '', producer_id: '' })
              router.get('/events', { env: environment })
            }}
            className="rounded-full px-3 py-1.5 text-[12px] font-medium text-ink-muted hover:bg-sunken"
          >
            Clear
          </button>
        </div>
      </div>

      {events.length === 0 ? (
        <Empty title="No events match" body="Adjust the filters, or publish something to this environment." />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Event</TH>
              <TH>Topic</TH>
              <TH>Producer</TH>
              <TH>Kind</TH>
              <TH>Severity</TH>
              <TH>Correlation</TH>
              <TH align="right">Time</TH>
            </TR>
          </THead>
          <TBody>
            {events.map((e) => (
              <TR key={e.id} href={`/events/${e.id}?env=${environment}`}>
                <TD>
                  <a href={`/events/${e.id}?env=${environment}`} className="font-medium text-ink hover:text-brand">
                    {e.event}
                  </a>
                  <div className="mono text-[11px] text-ink-faint">{e.id}</div>
                </TD>
                <TD><span className="mono">{e.topic}</span></TD>
                <TD>{e.producer ?? '—'}</TD>
                <TD><Badge tone={e.kind === 'task' ? 'brand' : e.kind === 'notification' ? 'caution' : 'neutral'}>{e.kind}</Badge></TD>
                <TD>{e.severity}</TD>
                <TD className="mono text-[11px] text-ink-faint">{e.correlation_id ?? '—'}</TD>
                <TD align="right" title={dateTime(e.timestamp)}>{ago(e.timestamp)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      {page.has_more && (
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={() => apply({ cursor: page.next_cursor ?? '' } as Record<string, string>)}
            className="rounded-full border border-line px-4 py-1.5 text-[12px] font-medium text-ink-muted hover:bg-sunken"
          >
            Load older
          </button>
        </div>
      )}
    </>
  )
}
