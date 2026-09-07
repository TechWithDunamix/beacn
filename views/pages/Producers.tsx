/** Producer registry — applications and services publishing to BEACN. */

import { Head, router } from '@inertiajs/react'
import { useState } from 'react'
import { ago, count, useCan } from '@/js/hooks'
import { api } from '@/js/api'
import {
  Badge,
  Button,
  Empty,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from '@/views/ui/kit'

interface Producer {
  id: string
  name: string
  slug: string
  environment: string
  description: string | null
  default_source: string | null
  status: string
  event_count: number
  last_event_at: string | null
  created_at: string
}

export default function Producers({
  environments,
  producers,
}: {
  environments: string[]
  producers: Producer[]
}) {
  const can = useCan()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', environment: environments[0] ?? 'development', description: '' })

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.post('/producers', { ...form, description: form.description || null })
      setOpen(false)
      setForm({ name: '', environment: environments[0] ?? 'development', description: '' })
      router.reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const toggle = async (p: Producer) => {
    await api.post(`/producers/${p.id}/status`, { active: p.status !== 'active' })
    router.reload()
  }

  return (
    <>
      <Head title="Producers" />
      <PageHeader
        title="Producers"
        subtitle={`${producers.length} registered`}
        actions={can('producers.write') && <Button variant="primary" onClick={() => setOpen(true)}>Register producer</Button>}
      />

      {producers.length === 0 ? (
        <Empty
          title="No producers"
          body="A producer is an app or service that publishes events — Orders API, Celery Workers, Deployment Service. Register one, then issue it an API key."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Environment</TH>
              <TH>Status</TH>
              <TH align="right">Events</TH>
              <TH align="right">Last activity</TH>
              <TH align="right" />
            </TR>
          </THead>
          <TBody>
            {producers.map((p) => (
              <TR key={p.id}>
                <TD>
                  <div className="font-medium text-ink">{p.name}</div>
                  <div className="mono text-[11px] text-ink-faint">{p.slug}</div>
                  {p.description && <div className="text-[11px] text-ink-muted">{p.description}</div>}
                </TD>
                <TD><Badge tone="neutral">{p.environment}</Badge></TD>
                <TD><Badge tone={p.status === 'active' ? 'ok' : 'neutral'} dot>{p.status}</Badge></TD>
                <TD align="right">{count(p.event_count)}</TD>
                <TD align="right">{ago(p.last_event_at)}</TD>
                <TD align="right">
                  {can('producers.write') && (
                    <Button size="xs" onClick={() => toggle(p)}>
                      {p.status === 'active' ? 'Disable' : 'Enable'}
                    </Button>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Register producer"
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} disabled={!form.name} onClick={submit}>Register</Button>
          </>
        }
      >
        <div className="space-y-4">
          {error && <p className="text-[12px] text-critical">{error}</p>}
          <Field label="Name" required>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Payments API" />
          </Field>
          <Field label="Environment">
            <Select value={form.environment} onChange={(e) => setForm({ ...form, environment: e.target.value })}>
              {environments.map((env) => (
                <option key={env} value={env}>{env}</option>
              ))}
            </Select>
          </Field>
          <Field label="Description">
            <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
        </div>
      </Modal>
    </>
  )
}
