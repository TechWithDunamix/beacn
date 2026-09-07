/** System configuration and bus health (read-only; configured via env vars). */

import { Head } from '@inertiajs/react'
import { Badge, KeyValue, PageHeader, Panel, PanelHeader } from '@/views/ui/kit'

interface Props {
  config: {
    app_env: string
    bus_backend: string
    queue_backend: string
    event_retention_hours: number
    task_retention_hours: number
    ingest_rate_per_minute: number
    heartbeat_ms: number
    environments: string[]
  }
  bus_health: { backend: string; ok: boolean; degraded?: boolean; detail: string }
}

export default function Settings({ config, bus_health }: Props) {
  return (
    <>
      <Head title="Settings" />
      <PageHeader
        title="Settings"
        subtitle="Configured through environment variables — see docs/DEPLOYMENT.md"
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel padded={false}>
          <PanelHeader title="Runtime" />
          <div className="px-5">
            <KeyValue
              rows={[
                { label: 'Environment', value: config.app_env },
                { label: 'Isolation environments', value: config.environments.join(', ') },
                { label: 'Event bus', value: <span className="mono">{config.bus_backend}</span> },
                { label: 'Job queue', value: <span className="mono">{config.queue_backend}</span> },
                { label: 'Heartbeat', value: `${config.heartbeat_ms} ms` },
              ]}
            />
          </div>
        </Panel>

        <Panel padded={false}>
          <PanelHeader title="Event bus health" />
          <div className="px-5">
            <KeyValue
              rows={[
                { label: 'Backend', value: bus_health.backend },
                {
                  label: 'Status',
                  value: (
                    <Badge tone={bus_health.ok ? 'ok' : bus_health.degraded ? 'caution' : 'critical'} dot>
                      {bus_health.ok ? 'ok' : bus_health.degraded ? 'degraded' : 'down'}
                    </Badge>
                  ),
                },
                { label: 'Detail', value: bus_health.detail },
              ]}
            />
          </div>
          {config.bus_backend === 'memory' && (
            <div className="border-t border-line px-5 py-3 text-[12px] text-ink-muted">
              In-process bus: fan-out is single-node. Set <span className="mono">BEACN_BUS=redis</span> for
              multi-instance delivery.
            </div>
          )}
        </Panel>

        <Panel padded={false}>
          <PanelHeader title="Retention" />
          <div className="px-5">
            <KeyValue
              rows={[
                { label: 'Events', value: `${config.event_retention_hours} h` },
                { label: 'Tasks', value: `${config.task_retention_hours} h` },
              ]}
            />
          </div>
        </Panel>

        <Panel padded={false}>
          <PanelHeader title="Ingestion limits" />
          <div className="px-5">
            <KeyValue
              rows={[
                { label: 'Publish rate / key', value: `${config.ingest_rate_per_minute.toLocaleString()} / min` },
                { label: 'Payload cap', value: '256 KiB' },
                { label: 'Batch cap', value: '500 events' },
                { label: 'Idempotency window', value: '24 h' },
              ]}
            />
          </div>
        </Panel>
      </div>
    </>
  )
}
