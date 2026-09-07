/** One event: metadata, full payload, delivery attempts. */

import { Head, Link } from '@inertiajs/react'
import { dateTime } from '@/js/hooks'
import {
  Badge,
  Empty,
  KeyValue,
  PageHeader,
  Panel,
  PanelHeader,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from '@/views/ui/kit'
import { JsonBlock } from '@/views/ui/Json'
import type { BeacnEvent } from '@/js/types'

interface Props {
  environment: string
  event: (BeacnEvent & { task?: { id: string; name: string; status: string } }) | null
  raw: Record<string, unknown> | null
  delivery_attempts: {
    connection_id: string
    outcome: string
    detail: string | null
    latency_ms: number | null
    acknowledged: boolean
    at: string
  }[]
}

const OUTCOME_TONE: Record<string, 'ok' | 'caution' | 'critical'> = {
  delivered: 'ok',
  dropped: 'caution',
  failed: 'critical',
}

export default function EventDetail({ environment, event, raw, delivery_attempts }: Props) {
  if (!event) {
    return (
      <>
        <Head title="Event not found" />
        <Empty
          title="No such event"
          body="It may have passed its retention window, or belong to another environment."
          action={<Link href={`/events?env=${environment}`} className="text-brand">Back to the explorer</Link>}
        />
      </>
    )
  }

  return (
    <>
      <Head title={event.event} />
      <PageHeader
        title={event.event}
        subtitle={<span className="mono">{event.id}</span>}
        breadcrumbs={[
          { label: 'Events', href: `/events?env=${environment}` },
          { label: event.event },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <Panel padded={false}>
            <PanelHeader title="Payload" description={`${JSON.stringify(raw ?? {}).length} bytes`} />
            <div className="p-4">
              <JsonBlock value={raw ?? {}} />
            </div>
          </Panel>

          <Panel padded={false}>
            <PanelHeader
              title="Delivery attempts"
              description="Recorded when a subscriber was connected at publish time (sampled under heavy fan-out)"
            />
            {delivery_attempts.length === 0 ? (
              <Empty title="No recorded deliveries" body="No connected subscriber at publish time, or sampling skipped it." />
            ) : (
              <Table className="rounded-none border-0">
                <THead>
                  <TR>
                    <TH>Connection</TH>
                    <TH>Outcome</TH>
                    <TH>Latency</TH>
                    <TH>Ack</TH>
                    <TH align="right">When</TH>
                  </TR>
                </THead>
                <TBody>
                  {delivery_attempts.map((a, i) => (
                    <TR key={i}>
                      <TD className="mono text-[11px]">{a.connection_id}</TD>
                      <TD><Badge tone={OUTCOME_TONE[a.outcome] ?? 'neutral'}>{a.outcome}</Badge></TD>
                      <TD>{a.latency_ms != null ? `${a.latency_ms}ms` : '—'}</TD>
                      <TD>{a.acknowledged ? 'yes' : '—'}</TD>
                      <TD align="right">{dateTime(a.at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel padded={false}>
            <PanelHeader title="Metadata" />
            <div className="px-5">
              <KeyValue
                rows={[
                  { label: 'Kind', value: <Badge tone="brand">{event.kind}</Badge> },
                  { label: 'Topic', value: <span className="mono">{event.topic}</span> },
                  { label: 'Producer', value: event.producer ?? '—' },
                  { label: 'Source', value: event.source ?? '—' },
                  { label: 'Environment', value: event.environment },
                  { label: 'Severity', value: event.severity },
                  { label: 'Schema', value: event.schema_version },
                  { label: 'Published', value: dateTime(event.timestamp) },
                  { label: 'Occurred', value: event.occurred_at ? dateTime(event.occurred_at) : '—' },
                ]}
              />
            </div>
          </Panel>

          <Panel padded={false}>
            <PanelHeader title="Correlation" />
            <div className="px-5">
              <KeyValue
                rows={[
                  { label: 'Correlation ID', value: <span className="mono text-[11px]">{event.correlation_id ?? '—'}</span> },
                  { label: 'Request ID', value: <span className="mono text-[11px]">{event.request_id ?? '—'}</span> },
                  { label: 'User', value: event.user_id ?? '—' },
                  { label: 'Organization', value: event.organization_id ?? '—' },
                  { label: 'Project', value: event.project_id ?? '—' },
                ]}
              />
            </div>
            {event.correlation_id && (
              <div className="border-t border-line px-5 py-3">
                <Link
                  href={`/events?env=${environment}&correlation_id=${event.correlation_id}`}
                  className="text-[12px] font-medium text-brand hover:underline"
                >
                  See the whole correlation chain →
                </Link>
              </div>
            )}
          </Panel>

          {event.delivery && (
            <Panel padded={false}>
              <PanelHeader title="Fan-out" />
              <div className="px-5">
                <KeyValue
                  rows={[
                    { label: 'Delivered', value: String(event.delivery.delivered) },
                    { label: 'Subscribers at publish', value: String(event.delivery.subscribers) },
                  ]}
                />
              </div>
            </Panel>
          )}
        </div>
      </div>
    </>
  )
}
