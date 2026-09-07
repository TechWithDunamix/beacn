/**
 * A minimal area sparkline. No chart dependency — one `<path>` and a gradient.
 * Purposeful use only: throughput over time, where the shape is the message.
 */

export function Sparkline({
  points,
  height = 100,
  className = '',
}: {
  points: number[]
  height?: number
  className?: string
}) {
  const width = 600
  const max = Math.max(1, ...points)
  const n = points.length
  if (n < 2) {
    return (
      <div
        className={`flex items-center justify-center text-[12px] text-ink-faint ${className}`}
        style={{ height }}
      >
        Not enough data yet
      </div>
    )
  }
  const step = width / (n - 1)
  const y = (v: number) => height - (v / max) * (height - 8) - 4
  const line = points.map((v, i) => `${i === 0 ? 'M' : 'L'} ${i * step} ${y(v)}`).join(' ')
  const area = `${line} L ${width} ${height} L 0 ${height} Z`

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={`w-full ${className}`}
      style={{ height }}
      role="img"
      aria-label="throughput over time"
    >
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--color-brand)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--color-brand)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#spark-fill)" />
      <path d={line} fill="none" stroke="var(--color-brand)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
