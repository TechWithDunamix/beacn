/** Realtime connection monitor. Operators can terminate a connection. */

import { Head, router } from '@inertiajs/react'
import { useState } from 'react'
import { ago, dateTime, useCan } from '@/js/hooks'
import { api } from '@/js/api'
import { Badge, Button, Empty, PageHeader, Table, TBody, TD, TH, THead, TR } from '@/views/ui/kit'

interface Conn {
  id: string
  transport: string
  status: string
  instance: string | null
  user_id: string | null
  organization_id: string | null
  client: string | null
  ip: string | null
  subscriptions: string[]
  events_sent: number
  events_dropped: number
  connected_at: string
  disconnected_at: string | null
  duration_seconds: number
}

function human(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

export default function Connections({ environment, connections }: { environment: string; connections: Conn[] }) {
  const can = useCan()
  const [busy, setBusy] = useState<string | null>(null)

  const terminate = async (id: string) => {
    setBusy(id)
    try {
      await api.post(`/connections/${id}/terminate`)
      router.reload()
    } finally {
      setBusy(null)
    }
  }

  const open = connections.filter((c) => c.status === 'open')

  return (
    <>
      <Head title="Connections" />
      <PageHeader
        title="Connections"
        subtitle={`${environment} · ${open.length} open of ${connections.length} recent`}
      />

      {connections.length === 0 ? (
        <Empty title="No connections" body="WebSocket and SSE connections appear here as consumers connect." />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Connection</TH>
              <TH>Transport</TH>
              <TH>Status</TH>
              <TH>Principal</TH>
              <TH>Subscriptions</TH>
              <TH align="right">Sent / dropped</TH>
              <TH align="right">Duration</TH>
              <TH align="right" />
            </TR>
          </THead>
          <TBody>
            {connections.map((c) => (
              <TR key={c.id}>
                <TD>
                  <div className="mono text-[11px] text-ink">{c.id}</div>
                  <div className="text-[11px] text-ink-faint">{c.client ?? c.ip ?? c.instance ?? '—'}</div>
                </TD>
                <TD>{c.transport.toUpperCase()}</TD>
                <TD><Badge tone={c.status === 'open' ? 'ok' : 'neutral'} dot>{c.status}</Badge></TD>
                <TD>{c.user_id ?? c.organization_id ?? '—'}</TD>
                <TD className="max-w-[220px]">
                  <span className="mono text-[11px] text-ink-muted">
                    {c.subscriptions.length ? c.subscriptions.join(', ') : '—'}
                  </span>
                </TD>
                <TD align="right">{c.events_sent} / {c.events_dropped}</TD>
                <TD align="right" title={dateTime(c.connected_at)}>
                  {c.status === 'open' ? human(c.duration_seconds) : ago(c.disconnected_at)}
                </TD>
                <TD align="right">
                  {c.status === 'open' && can('connections.write') && (
                    <Button size="xs" variant="danger" loading={busy === c.id} onClick={() => terminate(c.id)}>
                      Terminate
                    </Button>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </>
  )
}
