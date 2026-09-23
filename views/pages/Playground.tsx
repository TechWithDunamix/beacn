/**
 * Playground — open a real realtime connection as a chosen producer, subscribe
 * to topics, watch events arrive live, and publish test events to see them
 * come back over the same socket. Everything here goes through the same
 * `mint_realtime_token` / `ingest()` paths a real connection and producer use
 * (`routes/api/control.py` `playground_token` / `playground_publish`) — this
 * is a window onto the real system, not a simulation of it.
 */

import { Head } from '@inertiajs/react'
import { useEffect, useRef, useState } from 'react'
import { dateTime, useCan } from '@/js/hooks'
import { api, ApiRequestError } from '@/js/api'
import {
  Badge,
  Button,
  Empty,
  Field,
  Input,
  PageHeader,
  Panel,
  PanelHeader,
  Select,
  Textarea,
} from '@/views/ui/kit'

interface Producer {
  id: string
  name: string
}

type Frame = Record<string, unknown> & { type: string }

interface LogLine {
  id: number
  at: string
  direction: 'in' | 'out' | 'system'
  frame: Frame | { type: string; [k: string]: unknown }
}

let lineSeq = 0

function wsUrl(token: string): string {
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}/realtime?token=${encodeURIComponent(token)}`
}

export default function Playground({
  environment,
  producers,
}: {
  environment: string
  producers: Producer[]
}) {
  const can = useCan()
  const [producerId, setProducerId] = useState(producers[0]?.id ?? '')
  const [status, setStatus] = useState<'idle' | 'connecting' | 'open' | 'closed'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [topics, setTopics] = useState<string[]>([])
  const [topicInput, setTopicInput] = useState('')
  const [lines, setLines] = useState<LogLine[]>([])
  const [publishTopic, setPublishTopic] = useState('')
  const [publishEvent, setPublishEvent] = useState('')
  const [publishData, setPublishData] = useState('{}')
  const [publishing, setPublishing] = useState(false)
  const [publishError, setPublishError] = useState<string | null>(null)

  const socketRef = useRef<WebSocket | null>(null)
  const logRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => () => socketRef.current?.close(), [])

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight })
  }, [lines])

  const log = (direction: LogLine['direction'], frame: LogLine['frame']) => {
    lineSeq += 1
    setLines((prev) => [...prev.slice(-199), { id: lineSeq, at: new Date().toISOString(), direction, frame }])
  }

  const connect = async () => {
    if (!producerId) return
    setError(null)
    setStatus('connecting')
    try {
      const res = await api.post<{ token: string; expires_in: number }>('/playground/token', {
        environment,
        producer_id: producerId,
      })
      const socket = new WebSocket(wsUrl(res.token))
      socketRef.current = socket
      socket.onopen = () => setStatus('open')
      socket.onclose = () => {
        setStatus('closed')
        socketRef.current = null
      }
      socket.onerror = () => setError('the socket reported an error')
      socket.onmessage = (ev) => {
        try {
          log('in', JSON.parse(ev.data))
        } catch {
          log('in', { type: 'unparseable', raw: ev.data })
        }
      }
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : 'could not mint a token')
      setStatus('idle')
    }
  }

  const disconnect = () => {
    socketRef.current?.close(1000, 'closed by operator')
  }

  const send = (frame: Record<string, unknown>) => {
    socketRef.current?.send(JSON.stringify(frame))
    log('out', frame as LogLine['frame'])
  }

  const subscribe = () => {
    const topic = topicInput.trim()
    if (!topic || topics.includes(topic)) return
    send({ type: 'subscribe', topic, ref: topic })
    setTopics((prev) => [...prev, topic])
    setTopicInput('')
  }

  const unsubscribe = (topic: string) => {
    send({ type: 'unsubscribe', topic })
    setTopics((prev) => prev.filter((t) => t !== topic))
  }

  const publish = async () => {
    setPublishing(true)
    setPublishError(null)
    try {
      let data: unknown = undefined
      if (publishData.trim()) {
        try {
          data = JSON.parse(publishData)
        } catch {
          throw new Error('data must be valid JSON')
        }
      }
      await api.post('/playground/publish', {
        environment,
        producer_id: producerId,
        event: { event: publishEvent, topic: publishTopic || undefined, data },
      })
    } catch (e) {
      setPublishError(e instanceof Error ? e.message : 'publish failed')
    } finally {
      setPublishing(false)
    }
  }

  const connected = status === 'open'

  return (
    <>
      <Head title="Playground" />
      <PageHeader
        title="Playground"
        subtitle="Connect and publish as a producer, and watch it happen live."
      />

      {producers.length === 0 ? (
        <Empty
          title="No active producers in this environment"
          body={`Register a producer in ${environment} before opening the playground.`}
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
          <div className="space-y-4">
            <Panel>
              <div className="space-y-3">
                <Field label="Producer">
                  <Select
                    value={producerId}
                    disabled={connected || status === 'connecting'}
                    onChange={(e) => setProducerId(e.target.value)}
                  >
                    {producers.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </Select>
                </Field>
                <div className="flex items-center gap-2">
                  <Badge tone={connected ? 'ok' : status === 'connecting' ? 'brand' : 'neutral'} dot>
                    {status}
                  </Badge>
                  <Badge tone="neutral">{environment}</Badge>
                </div>
                {error && <p className="text-[12px] text-critical">{error}</p>}
                {connected ? (
                  <Button variant="secondary" onClick={disconnect}>Disconnect</Button>
                ) : (
                  <Button variant="primary" loading={status === 'connecting'} onClick={connect}>
                    Connect
                  </Button>
                )}
                {/* Watch-only: this token can subscribe to anything but carries no
                    scope beyond events:read — it cannot itself publish. */}
                <p className="text-[12px] text-ink-faint">
                  Mints a 10-minute watch-only token for this producer.
                </p>
              </div>
            </Panel>

            <Panel>
              <div className="space-y-3">
                <Field label="Subscribe to topic">
                  <div className="flex gap-2">
                    <Input
                      value={topicInput}
                      disabled={!connected}
                      placeholder="orders.created"
                      onChange={(e) => setTopicInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && subscribe()}
                    />
                    <Button disabled={!connected || !topicInput.trim()} onClick={subscribe}>Add</Button>
                  </div>
                </Field>
                {topics.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {topics.map((t) => (
                      <button
                        key={t}
                        onClick={() => unsubscribe(t)}
                        className="group inline-flex items-center gap-1 rounded-full bg-sunken px-2.5 py-0.5 text-[11px] text-ink-muted transition hover:bg-critical/10 hover:text-critical"
                        title="Unsubscribe"
                      >
                        {t}
                        <span aria-hidden>×</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </Panel>

            {can('events.publish') && (
              <Panel>
                <div className="space-y-3">
                  <Field label="Topic" hint="Optional — derived from the event name if omitted">
                    <Input value={publishTopic} onChange={(e) => setPublishTopic(e.target.value)} placeholder="orders.created" />
                  </Field>
                  <Field label="Event" required>
                    <Input value={publishEvent} onChange={(e) => setPublishEvent(e.target.value)} placeholder="order.created" />
                  </Field>
                  <Field label="Data" hint="JSON object">
                    <Textarea value={publishData} onChange={(e) => setPublishData(e.target.value)} />
                  </Field>
                  {publishError && <p className="text-[12px] text-critical">{publishError}</p>}
                  <Button
                    variant="primary"
                    loading={publishing}
                    disabled={!publishEvent.trim() || !producerId}
                    onClick={publish}
                  >
                    Publish test event
                  </Button>
                </div>
              </Panel>
            )}
          </div>

          <Panel padded={false} className="flex flex-col">
            <PanelHeader title="Live frames" description="Everything sent and received on this socket." />
            <div ref={logRef} className="mono max-h-[70vh] min-h-[300px] flex-1 space-y-1 overflow-y-auto px-5 py-4 text-[12px]">
              {lines.length === 0 && (
                <p className="text-ink-faint">Connect, then subscribe to a topic to see frames here.</p>
              )}
              {lines.map((line) => (
                <div key={line.id} className="flex gap-2">
                  <span className="shrink-0 text-ink-faint">{dateTime(line.at).split(' ')[1] ?? dateTime(line.at)}</span>
                  <span
                    className={
                      line.direction === 'out'
                        ? 'shrink-0 text-brand'
                        : line.direction === 'system'
                          ? 'shrink-0 text-ink-faint'
                          : 'shrink-0 text-ink'
                    }
                  >
                    {line.direction === 'out' ? '→' : line.direction === 'system' ? '·' : '←'}
                  </span>
                  <span className="min-w-0 whitespace-pre-wrap break-all text-ink-muted">
                    {JSON.stringify(line.frame)}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      )}
    </>
  )
}
