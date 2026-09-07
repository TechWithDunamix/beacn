/** API key management — create (secret shown once), rotate, revoke. */

import { Head, router } from '@inertiajs/react'
import { useState } from 'react'
import { ago, count, dateTime, useCan } from '@/js/hooks'
import { api } from '@/js/api'
import {
  Badge,
  Button,
  Checkbox,
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

interface Key {
  id: string
  name: string
  prefix: string
  masked: string
  environment: string
  scopes: string[]
  status: string
  producer: string | null
  request_count: number
  last_used_at: string | null
  expires_at: string | null
  created_at: string
}

interface Props {
  available_scopes: string[]
  producers: { id: string; name: string; environment: string }[]
  keys: Key[]
}

export default function ApiKeys({ available_scopes, producers, keys }: Props) {
  const can = useCan()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [secret, setSecret] = useState<string | null>(null)
  const [form, setForm] = useState({
    name: '',
    producer_id: producers[0]?.id ?? '',
    scopes: ['events:publish'] as string[],
    expires_in_days: '',
  })

  const toggleScope = (s: string) =>
    setForm((f) => ({
      ...f,
      scopes: f.scopes.includes(s) ? f.scopes.filter((x) => x !== s) : [...f.scopes, s],
    }))

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.post<{ key: { secret: string } }>('/keys', {
        name: form.name,
        producer_id: form.producer_id,
        scopes: form.scopes.join(' '),
        expires_in_days: form.expires_in_days ? Number(form.expires_in_days) : 0,
      })
      setSecret(res.key.secret)
      setOpen(false)
      router.reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (k: Key) => {
    if (!confirm(`Revoke ${k.name}? Requests with it will start failing immediately.`)) return
    await api.post(`/keys/${k.id}/revoke`, {})
    router.reload()
  }

  const rotate = async (k: Key) => {
    const res = await api.post<{ key: { secret: string } }>(`/keys/${k.id}/rotate`, {})
    setSecret(res.key.secret)
    router.reload()
  }

  return (
    <>
      <Head title="API keys" />
      <PageHeader
        title="API keys"
        subtitle={`${keys.filter((k) => k.status === 'active').length} active`}
        actions={
          can('apikeys.write') &&
          producers.length > 0 && <Button variant="primary" onClick={() => setOpen(true)}>Issue key</Button>
        }
      />

      {secret && (
        <div className="surface mb-4 border-brand/40 bg-brand-soft p-4">
          <p className="text-[13px] font-semibold text-ink">New API key — copy it now</p>
          <p className="text-[12px] text-ink-muted">Only a hash is stored. This is the only time it is shown.</p>
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 overflow-x-auto rounded-[var(--radius-sm)] border border-line bg-surface px-2.5 py-1.5 font-mono text-[12px]">
              {secret}
            </code>
            <Button size="sm" onClick={() => navigator.clipboard?.writeText(secret)}>Copy</Button>
            <Button size="sm" variant="ghost" onClick={() => setSecret(null)}>Dismiss</Button>
          </div>
        </div>
      )}

      {keys.length === 0 ? (
        <Empty
          title="No API keys"
          body={producers.length === 0 ? 'Register a producer first, then issue it a key.' : 'Issue a key to a producer so it can publish.'}
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Key</TH>
              <TH>Producer</TH>
              <TH>Environment</TH>
              <TH>Scopes</TH>
              <TH>Status</TH>
              <TH align="right">Requests</TH>
              <TH align="right">Last used</TH>
              <TH align="right" />
            </TR>
          </THead>
          <TBody>
            {keys.map((k) => (
              <TR key={k.id}>
                <TD className="font-medium text-ink">{k.name}</TD>
                <TD className="mono text-[11px]">{k.masked}</TD>
                <TD>{k.producer ?? '—'}</TD>
                <TD><Badge tone="neutral">{k.environment}</Badge></TD>
                <TD className="max-w-[240px] text-[11px] text-ink-muted">{k.scopes.join(', ')}</TD>
                <TD><Badge tone={k.status === 'active' ? 'ok' : 'neutral'} dot>{k.status}</Badge></TD>
                <TD align="right">{count(k.request_count)}</TD>
                <TD align="right" title={k.last_used_at ? dateTime(k.last_used_at) : ''}>{ago(k.last_used_at)}</TD>
                <TD align="right">
                  {can('apikeys.write') && k.status === 'active' && (
                    <div className="flex justify-end gap-1.5">
                      <Button size="xs" onClick={() => rotate(k)}>Rotate</Button>
                      <Button size="xs" variant="danger" onClick={() => revoke(k)}>Revoke</Button>
                    </div>
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
        title="Issue API key"
        description="The secret is returned once and never stored in the clear."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} disabled={!form.name || !form.producer_id} onClick={create}>
              Issue
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {error && <p className="text-[12px] text-critical">{error}</p>}
          <Field label="Name" required>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="orders prod" />
          </Field>
          <Field label="Producer" required>
            <Select value={form.producer_id} onChange={(e) => setForm({ ...form, producer_id: e.target.value })}>
              {producers.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.environment})</option>
              ))}
            </Select>
          </Field>
          <Field label="Scopes">
            <div className="grid grid-cols-2 gap-1.5">
              {available_scopes.map((s) => (
                <Checkbox key={s} label={<span className="mono text-[11px]">{s}</span>} checked={form.scopes.includes(s)} onChange={() => toggleScope(s)} />
              ))}
            </div>
          </Field>
          <Field label="Expires in (days)" hint="Blank means it never expires.">
            <Input type="number" value={form.expires_in_days} onChange={(e) => setForm({ ...form, expires_in_days: e.target.value })} />
          </Field>
        </div>
      </Modal>
    </>
  )
}
