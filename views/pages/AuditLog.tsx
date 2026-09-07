/** Administrative audit trail. Rows expand to show before/after. */

import { Head } from '@inertiajs/react'
import { useState } from 'react'
import { dateTime } from '@/js/hooks'
import { Badge, Empty, PageHeader, Table, TBody, TD, TH, THead, TR } from '@/views/ui/kit'
import { JsonBlock } from '@/views/ui/Json'

interface Event {
  id: string
  action: string
  actor: string
  origin: string
  resource_type: string | null
  resource_id: string | null
  resource_label: string | null
  environment: string | null
  before: unknown
  after: unknown
  at: string
}

export default function AuditLog({ events }: { events: Event[] }) {
  const [expanded, setExpanded] = useState<string | null>(null)

  return (
    <>
      <Head title="Audit log" />
      <PageHeader title="Audit log" subtitle="Every control-plane change: who, what, when" />

      {events.length === 0 ? (
        <Empty title="Nothing logged yet" body="Producer, key, topic, connection and role changes are recorded here." />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Action</TH>
              <TH>Actor</TH>
              <TH>Resource</TH>
              <TH>Origin</TH>
              <TH align="right">When</TH>
            </TR>
          </THead>
          <TBody>
            {events.map((e) => (
              <>
                <TR
                  key={e.id}
                  onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                  className={e.before || e.after ? 'cursor-pointer' : ''}
                >
                  <TD className="font-medium text-ink">{e.action}</TD>
                  <TD>{e.actor}</TD>
                  <TD>
                    {e.resource_label ?? e.resource_id ?? e.resource_type ?? '—'}
                    {e.environment && <span className="ml-2 text-[11px] text-ink-faint">{e.environment}</span>}
                  </TD>
                  <TD><Badge tone={e.origin === 'system' ? 'neutral' : 'brand'}>{e.origin}</Badge></TD>
                  <TD align="right" title={dateTime(e.at)}>{dateTime(e.at)}</TD>
                </TR>
                {expanded === e.id && (e.before || e.after) && (
                  <TR key={`${e.id}-detail`}>
                    <TD colSpan={5}>
                      <div className="grid gap-3 md:grid-cols-2">
                        <div>
                          <p className="eyebrow mb-1">Before</p>
                          <JsonBlock value={e.before ?? null} />
                        </div>
                        <div>
                          <p className="eyebrow mb-1">After</p>
                          <JsonBlock value={e.after ?? null} />
                        </div>
                      </div>
                    </TD>
                  </TR>
                )}
              </>
            ))}
          </TBody>
        </Table>
      )}
    </>
  )
}
