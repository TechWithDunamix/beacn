/**
 * The flash bag, rendered.
 *
 * Two kinds of message land here and they are treated differently:
 *
 * - `success` and `info` are transient — they auto-dismiss, because "Saved" is
 *   confirmation and nobody needs to close it.
 * - `error` and `warning` are not — a merchant who missed why a refund failed
 *   has no way to get the message back, so it stays until dismissed.
 *
 * `key` and `secret` are special. They carry a value shown exactly once — an
 * API key, a webhook signing secret — so they render as a copyable block that
 * never auto-dismisses and says plainly that it will not be shown again.
 */

import { useEffect, useState } from 'react'
import { cx, useShared } from '@/js/hooks'
import { Button } from './kit'
import { IconCheck, IconWarning } from './icons'

const TRANSIENT = new Set(['success', 'info'])
const ONE_TIME = new Set(['key', 'secret'])

export function FlashMessages() {
  const { flash } = useShared()
  // `flash` is absent on a page rendered without one, not empty.
  const entries = Object.entries(flash ?? {}).filter(([, message]) => Boolean(message))

  if (entries.length === 0) return null

  return (
    <div className="mx-auto mb-4 max-w-[1400px] space-y-2">
      {entries.map(([level, message]) =>
        ONE_TIME.has(level) ? (
          <OneTimeSecret key={level} label={level} value={message as string} />
        ) : (
          <FlashMessage key={level} level={level} message={message as string} />
        ),
      )}
    </div>
  )
}

function FlashMessage({ level, message }: { level: string; message: string }) {
  const [visible, setVisible] = useState(true)

  useEffect(() => {
    if (!TRANSIENT.has(level)) return
    const timer = setTimeout(() => setVisible(false), 5000)
    return () => clearTimeout(timer)
  }, [level])

  if (!visible) return null

  const TONE: Record<string, string> = {
    success: 'bg-[var(--color-positive-soft)] text-[var(--color-positive)]',
    error: 'bg-[var(--color-critical-soft)] text-[var(--color-critical)]',
    warning: 'bg-[var(--color-caution-soft)] text-[var(--color-caution)]',
    info: 'bg-[var(--color-info-soft)] text-[var(--color-info)]',
  }

  return (
    <div
      // `status` rather than `alert` for the transient ones: an assertive live
      // region interrupts a screen reader mid-sentence, which is right for a
      // failure and rude for "Saved".
      role={level === 'error' ? 'alert' : 'status'}
      className={cx(
        'flex items-start gap-2.5 rounded-[var(--radius-md)] px-3.5 py-2.5',
        TONE[level] ?? 'bg-[var(--color-sunken)] text-[var(--color-ink)]',
      )}
    >
      <span className="mt-0.5 shrink-0">
        {level === 'success' ? <IconCheck className="h-3.5 w-3.5" /> : <IconWarning className="h-3.5 w-3.5" />}
      </span>
      <p className="flex-1 text-[13px] font-medium">{message}</p>
      <button
        type="button"
        onClick={() => setVisible(false)}
        aria-label="Dismiss"
        className="-m-0.5 shrink-0 rounded p-0.5 opacity-60 hover:opacity-100"
      >
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
          <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  )
}

function OneTimeSecret({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
  const [visible, setVisible] = useState(true)

  if (!visible) return null

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access can be refused — an insecure origin, or a browser
      // policy. The value is on screen and selectable either way, so this is a
      // convenience failing rather than the feature failing.
    }
  }

  return (
    <div
      role="alert"
      className="rounded-[var(--radius-md)] border border-[var(--color-accent-line)] bg-[var(--color-accent-soft)] p-3.5"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[13px] font-semibold text-[var(--color-ink)]">
            Your new {label === 'key' ? 'API key' : 'signing secret'}
          </p>
          <p className="text-[12px] text-[var(--color-ink-soft)]">
            Copy it now — only a hash is stored, so it cannot be shown again.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setVisible(false)}
          aria-label="Dismiss"
          className="-m-0.5 shrink-0 rounded p-0.5 text-[var(--color-ink-faint)] hover:text-[var(--color-ink)]"
        >
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
            <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <div className="mt-2.5 flex items-center gap-2">
        <code className="flex-1 overflow-x-auto rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface)] px-2.5 py-1.5 font-[family-name:var(--font-mono)] text-[12px] text-[var(--color-ink)]">
          {value}
        </code>
        <Button size="sm" onClick={copy}>
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
    </div>
  )
}
