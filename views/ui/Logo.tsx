/**
 * The BEACN mark — a stylised broadcast pulse — and the wordmark.
 *
 * Geometry and weights follow JANUS's Logo: a compact glyph, `currentColor`
 * throughout so it inherits ink, and a wordmark that is the glyph plus the name
 * in a semibold tracking-tight setting.
 */

export function Mark({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden>
      <circle cx="12" cy="12" r="3" fill="currentColor" />
      <path
        d="M6.5 6.5a7.8 7.8 0 0 0 0 11M17.5 6.5a7.8 7.8 0 0 1 0 11M3.5 3.5a12 12 0 0 0 0 17M20.5 3.5a12 12 0 0 1 0 17"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function Wordmark({ className = 'h-6' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 text-ink ${className}`}>
      <Mark className="h-[1.15em] w-[1.15em] text-brand" />
      <span className="text-[1em] font-semibold tracking-[-0.04em]">BEACN</span>
    </span>
  )
}
