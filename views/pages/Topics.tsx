/** Topic management — visibility, retention, persistence. */

import { Head, router } from '@inertiajs/react'
import { useState } from 'react'
import { ago, count } from '@/js/hooks'
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
import { useCan } from '@/js/hooks'

interface Topic {
  id: string
  name: string
  visibility: string
  persist: boolean
  retention_hours: number | null
  description: string | null
  propagate_to: string[]
  event_count: number
  subscriber_count: number
  last_event_at: string | null
}

const emptyForm = {
  name: '', visibility: 'public', persist: true, retention_hours: '', description: '',
  propagate_to: [] as string[],
}

const VIS_TONE: Record<string, 'ok' | 'caution' | 'critical'> = {
  public: 'ok',
  private: 'caution',
  internal: 'critical',
}

export default function Topics({ environment, topics }: { environment: string; topics: Topic[] }) {
  const can = useCan()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [propagateInput, setPropagateInput] = useState('')
  const [error, setError] = useState<string | null>(null)

  const edit = (topic: Topic) => {
    setForm({
      name: topic.name,
      visibility: topic.visibility,
      persist: topic.persist,
      retention_hours: topic.retention_hours ? String(topic.retention_hours) : '',
      description: topic.description || '',
      propagate_to: topic.propagate_to,
    })
    setPropagateInput('')
    setError(null)
    setOpen(true)
  }

  const addPropagateTarget = () => {
    const name = propagateInput.trim()
    if (!name || name === form.name || form.propagate_to.includes(name)) {
      setPropagateInput('')
      return
    }
    setForm({ ...form, propagate_to: [...form.propagate_to, name] })
    setPropagateInput('')
  }

  const removePropagateTarget = (name: string) => {
    setForm({ ...form, propagate_to: form.propagate_to.filter((t) => t !== name) })
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.post('/topics', {
        environment,
        name: form.name,
        visibility: form.visibility,
        persist: form.persist,
        retention_hours: form.retention_hours ? Number(form.retention_hours) : null,
        description: form.description || null,
        propagate_to: form.propagate_to,
      })
      setOpen(false)
      setForm(emptyForm)
      router.reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Head title="Topics" />
      <PageHeader
        title="Topics"
        subtitle={`${environment} · ${topics.length}`}
        actions={can('topics.write') && (
          <Button variant="primary" onClick={() => { setForm(emptyForm); setPropagateInput(''); setError(null); setOpen(true) }}>
            Configure topic
          </Button>
        )}
      />

      {topics.length === 0 ? (
        <Empty
          title="No configured topics"
          body="A topic works without a row — configure one only to pin its visibility, retention, or turn off persistence."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Visibility</TH>
              <TH>Persist</TH>
              <TH>Propagates to</TH>
              <TH>Retention</TH>
              <TH align="right">Events</TH>
              <TH align="right">Subscribers</TH>
              <TH align="right">Last event</TH>
            </TR>
          </THead>
          <TBody>
            {topics.map((t) => (
              <TR key={t.id} onClick={can('topics.write') ? () => edit(t) : undefined}>
                <TD>
                  <span className="mono font-medium text-ink">{t.name}</span>
                  {t.description && <div className="text-[11px] text-ink-faint">{t.description}</div>}
                </TD>
                <TD><Badge tone={VIS_TONE[t.visibility] ?? 'neutral'}>{t.visibility}</Badge></TD>
                <TD>{t.persist ? 'yes' : <span className="text-ink-faint">no</span>}</TD>
                <TD>
                  {t.propagate_to.length === 0 ? (
                    <span className="text-ink-faint">—</span>
                  ) : (
                    <span className="mono text-[11px] text-ink-soft">{t.propagate_to.join(', ')}</span>
                  )}
                </TD>
                <TD>{t.retention_hours ? `${t.retention_hours}h` : 'default'}</TD>
                <TD align="right">{count(t.event_count)}</TD>
                <TD align="right">{count(t.subscriber_count)}</TD>
                <TD align="right">{ago(t.last_event_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Configure topic"
        description="Creates the topic row if it does not exist."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} onClick={submit} disabled={!form.name}>Save</Button>
          </>
        }
      >
        <div className="space-y-4">
          {error && <p className="text-[12px] text-critical">{error}</p>}
          <Field label="Topic name" required>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="payments" />
          </Field>
          <Field
            label="Propagate to"
            hint="Every event published to this topic also fires on each one listed here — one hop only, so a cycle between two topics can't loop forever."
          >
            <div className="flex gap-2">
              <Input
                value={propagateInput}
                onChange={(e) => setPropagateInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addPropagateTarget()
                  }
                }}
                placeholder="audit-log"
                list="topic-names"
              />
              <datalist id="topic-names">
                {topics
                  .map((t) => t.name)
                  .filter((name) => name !== form.name && !form.propagate_to.includes(name))
                  .map((name) => <option key={name} value={name} />)}
              </datalist>
              <Button onClick={addPropagateTarget} disabled={!propagateInput.trim()}>Add</Button>
            </div>
            {form.propagate_to.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {form.propagate_to.map((name) => (
                  <span
                    key={name}
                    className="mono inline-flex items-center gap-1.5 rounded-full bg-sunken px-2.5 py-0.5 text-[11px] font-medium text-ink-soft"
                  >
                    {name}
                    <button
                      type="button"
                      onClick={() => removePropagateTarget(name)}
                      aria-label={`Remove ${name}`}
                      className="text-ink-faint hover:text-critical"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </Field>
          <Field label="Visibility">
            <Select value={form.visibility} onChange={(e) => setForm({ ...form, visibility: e.target.value })}>
              <option value="public">public — anyone in the environment</option>
              <option value="private">private — explicit grant required</option>
              <option value="internal">internal — operators only</option>
            </Select>
          </Field>
          <Field label="Retention (hours)" hint="Blank uses the global default.">
            <Input
              type="number"
              value={form.retention_hours}
              onChange={(e) => setForm({ ...form, retention_hours: e.target.value })}
            />
          </Field>
          <Checkbox
            label="Persist events to the durable store"
            hint="Off makes this a live-only topic — no history, no replay."
            checked={form.persist}
            onChange={(e) => setForm({ ...form, persist: e.target.checked })}
          />
          <Field label="Description">
            <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
        </div>
      </Modal>
    </>
  )
}
