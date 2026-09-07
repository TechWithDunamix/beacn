/**
 * The shared interface vocabulary.
 *
 * This is the commerce dashboard's component set, and it is deliberately
 * unchanged: the same props, the same semantics, the same geometry — pill
 * controls, a 1.1rem card radius, hairline borders, the same density. A page
 * written against `Panel`, `Table`, `Stat` and `Badge` means exactly what it
 * meant there.
 *
 * What differs is the palette, and all of it lives in `js/app.css`. These
 * components name semantic tokens — `surface`, `line`, `ink-muted`,
 * `critical` — and never a hue, which is why swapping in nobus.io's blues
 * re-skinned forty screens without touching this file's layout at all.
 *
 * Three rules the components encode:
 *
 * - **Hairlines separate; shadows float.** Only `Popover` and `Modal` carry a
 *   shadow, because only they are genuinely above the page.
 * - **Colour means a state.** A `Badge` tone maps to something real. Nothing
 *   is coloured to be interesting.
 * - **Empty, loading and error are components, not afterthoughts.** A table
 *   with no rows renders `Empty`, which says what would be here and what to do
 *   about it — never a blank rectangle.
 */

import { Link } from '@inertiajs/react'
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { useEffect, useRef, useState } from 'react'
import { cx } from '@/js/hooks'
import { IconClose, IconSearch, IconWarning } from './icons'

const ring = 'ring-focus'

/* -- buttons ------------------------------------------------------------ */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle'

const variants: Record<Variant, string> = {
  // The one action a screen most wants. `bg-primary`/`text-on-primary` is a
  // pair defined per mode — see js/app.css. It is deliberately not
  // `bg-ink text-white`: `ink` is the body-text colour and inverts, so that
  // produced a white button with white text in dark mode.
  primary: 'bg-primary text-on-primary hover:bg-primary-hover',
  // Plum outline pill.
  secondary: 'border border-brand/40 bg-surface text-brand hover:bg-brand-soft',
  subtle:
    'bg-sunken text-ink-muted hover:bg-line',
  ghost:
    'text-ink-muted hover:bg-sunken hover:text-ink',
  danger:
    'border border-critical/40 bg-surface text-critical hover:bg-critical-soft',
}

type Size = 'xs' | 'sm' | 'md'

/**
 * The previous prop name for `variant`, and the values it took.
 *
 * Aliased rather than renamed across every page: a compatibility map in one
 * file is cheaper to read — and to remove later — than the same rename spread
 * over forty call sites, and it cannot be half-done.
 */
type LegacyTone = 'primary' | 'default' | 'ghost' | 'danger'

const legacyTone: Record<LegacyTone, Variant> = {
  primary: 'primary',
  default: 'secondary',
  ghost: 'ghost',
  danger: 'danger',
}

const pad = (size: Size) =>
  size === 'xs' ? 'h-7 px-3 text-[11px]' : size === 'sm' ? 'h-9 px-4 text-[12px]' : 'h-10 px-5 text-[13px]'

const base =
  `inline-flex items-center justify-center gap-1.5 rounded-full font-medium transition ${ring} ` +
  'disabled:pointer-events-none disabled:opacity-40 whitespace-nowrap'

export function Button({
  variant,
  tone,
  size = 'md',
  className = '',
  loading,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  /** The previous name for `variant`. See `legacyTone`. */
  tone?: LegacyTone
  size?: Size
  loading?: boolean
}) {
  const resolved: Variant = variant ?? (tone ? legacyTone[tone] : 'secondary')
  return (
    <button
      type="button"
      className={cx(base, pad(size), variants[resolved], className)}
      // A loading button must not be pressable again, or a slow save becomes
      // two saves.
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <Spinner />}
      {children}
    </button>
  )
}

export function LinkButton({
  href,
  variant,
  tone,
  size = 'md',
  className = '',
  children,
  ...rest
}: {
  href: string
  variant?: Variant
  tone?: LegacyTone
  size?: Size
  className?: string
  children: ReactNode
} & Omit<
  React.ComponentProps<typeof Link>,
  'href' | 'className' | 'children' | 'size' | 'tone'
>) {
  const resolved: Variant = variant ?? (tone ? legacyTone[tone] : 'secondary')
  return (
    <Link href={href} className={cx(base, pad(size), variants[resolved], className)} {...rest}>
      {children}
    </Link>
  )
}

/** The previous name, kept so existing pages keep compiling. */
export const ButtonLink = LinkButton

function Spinner() {
  return (
    <svg className="h-3 w-3 animate-spin" viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

/* -- page scaffolding --------------------------------------------------- */

export function PageHeader({
  title,
  subtitle,
  description,
  actions,
  breadcrumbs,
  breadcrumb,
}: {
  title: string
  subtitle?: ReactNode
  /** The previous name for `subtitle`. */
  description?: ReactNode
  actions?: ReactNode
  breadcrumbs?: { label: string; href?: string }[]
  /** The previous name for `breadcrumbs`. */
  breadcrumb?: { label: string; href?: string }[]
}) {
  const crumbs = breadcrumbs ?? breadcrumb
  const under = subtitle ?? description

  return (
    <div className="mb-6">
      {crumbs && crumbs.length > 0 && (
        <nav className="mb-2 flex items-center gap-1.5 text-[12px] text-ink-faint">
          {crumbs.map((crumb, index) => (
            <span key={crumb.label} className="flex items-center gap-1.5">
              {index > 0 && <span aria-hidden>/</span>}
              {crumb.href ? (
                <Link
                  href={crumb.href}
                  className="transition hover:text-ink"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span>{crumb.label}</span>
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {/* 20px, not 32. This is a page inside an application, not a landing
              page — an outsized heading pushes the content below the fold. */}
          <h1 className="truncate text-[20px] font-semibold tracking-[-0.02em] text-ink">
            {title}
          </h1>
          {under && <div className="mt-1 text-[13px] text-ink-muted">{under}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-[13px] font-semibold text-ink">{children}</h2>
      {action}
    </div>
  )
}

export function Panel({
  children,
  className = '',
  padded = true,
}: {
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return <div className={cx('surface', padded && 'p-5', className)}>{children}</div>
}

export function PanelHeader({
  title,
  description,
  action,
}: {
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-[13px] font-semibold text-ink">{title}</h2>
        {description && <div className="mt-0.5 text-[12px] text-ink-muted">{description}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

/* -- badges ------------------------------------------------------------- */

export type Tone =
  | 'neutral'
  | 'ok'
  | 'caution'
  | 'abnormal'
  | 'critical'
  | 'brand'
  // The previous names, so pages written against them keep compiling.
  | 'positive'
  | 'info'
  | 'accent'

const badgeTone: Record<Tone, string> = {
  neutral: 'bg-sunken text-ink-muted',
  ok: 'bg-ok-soft text-ok dark:bg-ok/15',
  positive: 'bg-ok-soft text-ok dark:bg-ok/15',
  caution: 'bg-caution-soft text-caution dark:bg-caution/15',
  abnormal: 'bg-abnormal-soft text-abnormal dark:bg-abnormal/15',
  critical: 'bg-critical-soft text-critical dark:bg-critical/15',
  brand: 'bg-brand-soft text-brand dark:bg-brand/15',
  accent: 'bg-brand-soft text-brand dark:bg-brand/15',
  info: 'bg-brand-soft text-brand dark:bg-brand/15',
}

export function Badge({
  children,
  tone = 'neutral',
  dot,
}: {
  children: ReactNode
  tone?: Tone
  dot?: boolean
}) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5',
        'text-[11px] font-medium leading-5 whitespace-nowrap',
        badgeTone[tone],
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  )
}

/**
 * The status vocabulary, in one place.
 *
 * Every screen showing a status reads this, so `refunded` is never amber on one
 * page and red on another.
 */
const STATUS_TONE: Record<string, Tone> = {
  pending: 'caution', paid: 'ok', processing: 'brand', shipped: 'brand',
  delivered: 'ok', cancelled: 'neutral', refunded: 'critical',
  partially_refunded: 'caution',
  succeeded: 'ok', failed: 'critical',
  unfulfilled: 'caution', fulfilled: 'ok', partially_fulfilled: 'caution',
  returned: 'neutral', unpaid: 'neutral', authorized: 'brand',
  active: 'ok', draft: 'neutral', archived: 'neutral', paused: 'caution',
  scheduled: 'brand', completed: 'neutral', disabled: 'neutral',
  expired: 'neutral', exhausted: 'neutral', published: 'ok', hidden: 'neutral',
  in_stock: 'ok', low_stock: 'caution', out_of_stock: 'critical', untracked: 'neutral',
  connected: 'ok', disconnected: 'neutral', error: 'critical', verified: 'ok',
  sending: 'brand', queued: 'neutral', running: 'brand', complete: 'ok',
  recovered: 'ok', notified: 'brand',
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="text-ink-faint">—</span>
  return (
    <Badge tone={STATUS_TONE[status] ?? 'neutral'} dot>
      {status.replace(/_/g, ' ')}
    </Badge>
  )
}

/* -- tables ------------------------------------------------------------- */

export function Table({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    // The wrapper scrolls, not the page. A wide table must never make the whole
    // document scroll sideways.
    <div className={cx('surface overflow-hidden', className)}>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">{children}</table>
      </div>
    </div>
  )
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead className="border-b border-line bg-sunken/60">
      {children}
    </thead>
  )
}

export function TH({
  children,
  align = 'left',
  className = '',
}: {
  children?: ReactNode
  align?: 'left' | 'right' | 'center'
  className?: string
}) {
  return (
    <th
      className={cx(
        'px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-faint whitespace-nowrap',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        align === 'left' && 'text-left',
        className,
      )}
    >
      {children}
    </th>
  )
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-line">{children}</tbody>
}

export function TR({
  children,
  href,
  onClick,
  className = '',
}: {
  children: ReactNode
  href?: string
  /** Makes the row a disclosure control — used by the audit log, where a row
   *  expands to show its before/after values rather than navigating. Ignored
   *  when `href` is set, since a row cannot both navigate and expand. */
  onClick?: () => void
  className?: string
}) {
  if (href) {
    return (
      <tr
        className={cx('row-hover cursor-pointer', className)}
        onClick={(event) => {
          const target = event.target as HTMLElement
          if (target.closest('a,button,input,select,label')) return
          // The first anchor in the row is its destination by convention — the
          // identifier cell. No marker attribute, because Inertia's `Link`
          // rejects props it does not know about.
          event.currentTarget.querySelector<HTMLAnchorElement>('a')?.click()
        }}
      >
        {children}
      </tr>
    )
  }
  if (onClick) {
    return (
      <tr
        className={cx('row-hover cursor-pointer', className)}
        onClick={(event) => {
          const target = event.target as HTMLElement
          if (target.closest('a,button,input,select,label')) return
          onClick()
        }}
      >
        {children}
      </tr>
    )
  }
  return <tr className={cx('row-hover', className)}>{children}</tr>
}

export function TD({
  children,
  align = 'left',
  colSpan,
  className = '',
  title,
}: {
  children?: ReactNode
  align?: 'left' | 'right' | 'center'
  /** For a detail row that spans the whole table. */
  colSpan?: number
  className?: string
  /** Native tooltip — used for an absolute timestamp behind a relative one. */
  title?: string
}) {
  return (
    <td
      colSpan={colSpan}
      title={title}
      className={cx(
        'px-4 py-3 align-middle text-ink',
        align === 'right' && 'text-right num',
        align === 'center' && 'text-center',
        className,
      )}
    >
      {children}
    </td>
  )
}

/* -- empty / loading / error -------------------------------------------- */

export function Empty({
  title,
  body,
  action,
  icon,
}: {
  title: string
  body?: string
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    // Never a blank rectangle. An empty state says what would be here, why it
    // is not, and what to do — the difference between "no data" and a screen
    // that looks broken.
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      {icon && (
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-sunken text-ink-faint">
          {icon}
        </div>
      )}
      <p className="text-[14px] font-medium text-ink">{title}</p>
      {body && <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-ink-muted">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/**
 * The placeholder a deferred prop shows before it arrives.
 *
 * Shaped like the thing that is coming, so the layout does not jump when it
 * does — a spinner would tell the reader less and move more.
 */
export function Skeleton({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={cx('space-y-2.5', className)} aria-hidden>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton h-4" style={{ width: `${100 - index * 7}%` }} />
      ))}
    </div>
  )
}

export function StatSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="surface grid grid-cols-2 divide-line overflow-hidden sm:grid-cols-4 sm:divide-x">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="p-5">
          <div className="skeleton h-3 w-16" />
          <div className="skeleton mt-3 h-7 w-24" />
        </div>
      ))}
    </div>
  )
}

export function ErrorState({
  title = 'Something went wrong',
  body,
  onRetry,
}: {
  title?: string
  body?: string
  onRetry?: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-critical-soft text-critical">
        <IconWarning className="h-5 w-5" />
      </div>
      <p className="text-[14px] font-medium text-ink">{title}</p>
      {body && <p className="mt-1.5 max-w-sm text-[13px] text-ink-muted">{body}</p>}
      {onRetry && (
        <Button className="mt-5" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

/* -- figures ------------------------------------------------------------ */

/**
 * A row of figures, divided by hairlines rather than boxed as cards.
 *
 * Cards in a grid put five borders around each number and turn a summary into a
 * patchwork. One bordered container with dividers reads as one object.
 */
export function StatRow({ children }: { children: ReactNode }) {
  return (
    <div className="surface grid grid-cols-2 divide-line overflow-hidden sm:grid-cols-3 sm:divide-x lg:grid-cols-4">
      {children}
    </div>
  )
}

export function Stat({
  label,
  value,
  hint,
  trend,
  tone,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  trend?: number | null
  tone?: Tone
}) {
  return (
    <div className="p-5">
      <div className="eyebrow">{label}</div>
      <div
        className={cx(
          'mt-2 text-[22px] font-semibold tracking-[-0.02em] num',
          tone === 'critical' && 'text-critical',
          (tone === 'ok' || tone === 'positive') && 'text-ok',
          !tone && 'text-ink',
        )}
      >
        {value}
      </div>
      {(hint || (trend !== undefined && trend !== null)) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[12px] text-ink-muted">
          {trend !== undefined && trend !== null && (
            <span className={cx('font-medium num', trend >= 0 ? 'text-ok' : 'text-critical')}>
              {trend >= 0 ? '↑' : '↓'} {Math.abs(trend * 100).toFixed(1)}%
            </span>
          )}
          {hint}
        </div>
      )}
    </div>
  )
}

/* -- forms -------------------------------------------------------------- */

export function Field({
  label,
  hint,
  error,
  children,
  required,
  className = '',
}: {
  label?: ReactNode
  hint?: ReactNode
  error?: string
  children: ReactNode
  required?: boolean
  className?: string
}) {
  return (
    <div className={cx('space-y-1.5', className)}>
      {label && (
        <label className="block text-[12px] font-medium text-ink">
          {label}
          {required && <span className="ml-0.5 text-critical">*</span>}
        </label>
      )}
      {children}
      {/* The error replaces the hint rather than stacking under it: two lines
          of guidance under one field is where a form starts to feel anxious. */}
      {error ? (
        <p className="text-[12px] text-critical">{error}</p>
      ) : (
        hint && <p className="text-[12px] text-ink-muted">{hint}</p>
      )}
    </div>
  )
}

const control =
  'w-full rounded-[var(--radius-sm)] border bg-surface px-3 py-2 text-[13px] text-ink ' +
  'placeholder:text-ink-faint transition focus:border-brand focus:outline-none ' +
  'disabled:bg-sunken disabled:text-ink-faint'

export function Input({
  invalid,
  className = '',
  ...rest
}: { invalid?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx(control, invalid ? 'border-critical' : 'border-line', className)}
      {...rest}
    />
  )
}

export function Textarea({
  invalid,
  className = '',
  ...rest
}: { invalid?: boolean } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(
        control,
        'min-h-24 resize-y leading-relaxed',
        invalid ? 'border-critical' : 'border-line',
        className,
      )}
      {...rest}
    />
  )
}

export function Select({
  children,
  invalid,
  className = '',
  ...rest
}: { children: ReactNode; invalid?: boolean } & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cx(
        control,
        'appearance-none bg-[length:14px] bg-[right_10px_center] bg-no-repeat pr-9',
        invalid ? 'border-critical' : 'border-line',
        className,
      )}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='%2394a3b8' stroke-width='1.5'%3E%3Cpath d='M4 6l4 4 4-4'/%3E%3C/svg%3E\")",
      }}
      {...rest}
    >
      {children}
    </select>
  )
}

export function Checkbox({
  label,
  hint,
  className = '',
  ...rest
}: { label: ReactNode; hint?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={cx('flex cursor-pointer items-start gap-2.5', className)}>
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 rounded-[5px] border-line accent-brand"
        {...rest}
      />
      <span className="min-w-0">
        <span className="block text-[13px] text-ink">{label}</span>
        {hint && <span className="block text-[12px] text-ink-muted">{hint}</span>}
      </span>
    </label>
  )
}

/* -- filters ------------------------------------------------------------ */

export function Tabs({
  tabs,
  active,
  onSelect,
}: {
  tabs: { key: string; label: string; count?: number }[]
  active: string
  onSelect: (key: string) => void
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          onClick={() => onSelect(tab.key)}
          className={cx(
            'whitespace-nowrap rounded-full px-3.5 py-1.5 text-[12px] font-medium transition',
            tab.key === active
              ? 'bg-primary text-on-primary'
              : 'text-ink-muted hover:bg-sunken hover:text-ink',
          )}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className={cx('ml-1.5 num', tab.key === active ? 'opacity-70' : 'text-ink-faint')}>
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  className = '',
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}) {
  return (
    <div className={cx('relative', className)}>
      <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="pl-9"
      />
    </div>
  )
}

/* -- overlays ----------------------------------------------------------- */

export function Popover({
  trigger,
  children,
  align = 'right',
  className = '',
}: {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode
  children: (props: { close: () => void }) => ReactNode
  align?: 'left' | 'right'
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDown(event: MouseEvent) {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={ref} className="relative">
      {trigger({ open, toggle: () => setOpen((value) => !value) })}
      {open && (
        <div
          className={cx(
            'surface card-shadow absolute z-40 mt-2 min-w-52 p-1.5',
            align === 'right' ? 'right-0' : 'left-0',
            className,
          )}
        >
          {children({ close: () => setOpen(false) })}
        </div>
      )}
    </div>
  )
}

export function MenuItem({
  children,
  onClick,
  href,
  tone,
  icon,
}: {
  children: ReactNode
  onClick?: () => void
  href?: string
  tone?: 'danger'
  /** Drawn before the label, at the menu's own size. Added for Janus, where
   *  most menus are pickers of things that have a glyph — a gateway, a theme,
   *  a sign-out. */
  icon?: ReactNode
}) {
  const className = cx(
    'flex w-full items-center gap-2.5 rounded-[var(--radius-sm)] px-3 py-2 text-left text-[13px] transition',
    'hover:bg-sunken',
    tone === 'danger' ? 'text-critical' : 'text-ink',
  )
  const body = (
    <>
      {icon && <span className="shrink-0 text-ink-faint">{icon}</span>}
      {children}
    </>
  )
  if (href) {
    return (
      <Link href={href} className={className}>
        {body}
      </Link>
    )
  }
  return (
    <button type="button" onClick={onClick} className={className}>
      {body}
    </button>
  )
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = 'md',
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  width?: 'sm' | 'md' | 'lg' | 'xl'
}) {
  useEffect(() => {
    if (!open) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    // The page behind must not scroll while a modal is open, or dismissing it
    // returns the reader somewhere they did not choose to be.
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [open, onClose])

  if (!open) return null

  const widths = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-5xl' }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:p-8">
      <div className="fixed inset-0 bg-[color-mix(in_srgb,var(--color-ink)_28%,transparent)] backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx('surface modal-shadow relative z-10 w-full', widths[width])}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-[14px] font-semibold text-ink">{title}</h2>
            {description && <div className="mt-0.5 text-[12px] text-ink-muted">{description}</div>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-m-1.5 rounded-full p-1.5 text-ink-faint transition hover:bg-sunken hover:text-ink"
          >
            <IconClose className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-5">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-4">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

/* -- pagination --------------------------------------------------------- */

export function Pager({
  page,
  pages,
  total,
  onPage,
}: {
  page: number
  pages: number
  total: number
  onPage: (page: number) => void
}) {
  if (pages <= 1) {
    return (
      <div className="px-4 py-3 text-[12px] text-ink-faint">
        {total} {total === 1 ? 'result' : 'results'}
      </div>
    )
  }
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <span className="text-[12px] text-ink-faint num">
        Page {page} of {pages} · {total} results
      </span>
      <div className="flex gap-2">
        <Button size="xs" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </Button>
        <Button size="xs" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </Button>
      </div>
    </div>
  )
}

/* -- misc --------------------------------------------------------------- */

export function Timeline({
  entries,
}: {
  entries: {
    id: number | string
    title: ReactNode
    meta?: ReactNode
    body?: ReactNode
    tone?: Tone
  }[]
}) {
  if (entries.length === 0) {
    return <Empty title="Nothing yet" body="Activity will appear here as it happens." />
  }
  const dot: Record<Tone, string> = {
    neutral: 'bg-ink-faint',
    ok: 'bg-ok',
    positive: 'bg-ok',
    caution: 'bg-caution',
    abnormal: 'bg-abnormal',
    critical: 'bg-critical',
    brand: 'bg-brand',
    accent: 'bg-brand',
    info: 'bg-brand',
  }
  return (
    <ol className="relative space-y-4">
      {/* One continuous rule behind the dots, rather than a segment per entry —
          which would show a gap wherever two entries differ in height. */}
      <div className="absolute bottom-2 left-[3.5px] top-2 w-px bg-line" aria-hidden />
      {entries.map((entry) => (
        <li key={entry.id} className="relative flex gap-3">
          <span
            className={cx(
              'mt-1.5 h-2 w-2 shrink-0 rounded-full ring-4 ring-surface',
              dot[entry.tone ?? 'neutral'],
            )}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-[13px] text-ink">{entry.title}</span>
              {entry.meta && <span className="text-[12px] text-ink-faint">{entry.meta}</span>}
            </div>
            {entry.body && <div className="mt-0.5 text-[12px] text-ink-muted">{entry.body}</div>}
          </div>
        </li>
      ))}
    </ol>
  )
}

export function KeyValue({ rows }: { rows: { label: ReactNode; value: ReactNode }[] }) {
  return (
    <dl className="divide-y divide-line">
      {rows.map((row, index) => (
        <div key={index} className="flex items-baseline justify-between gap-4 py-2.5">
          <dt className="text-[12px] text-ink-muted">{row.label}</dt>
          <dd className="text-right text-[13px] font-medium text-ink num">
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function Banner({
  tone = 'neutral',
  title,
  children,
  action,
  className = '',
}: {
  tone?: Tone
  title?: ReactNode
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  const surfaces: Record<Tone, string> = {
    neutral: 'bg-sunken',
    ok: 'bg-ok-soft dark:bg-ok/10',
    positive: 'bg-ok-soft dark:bg-ok/10',
    caution: 'bg-caution-soft dark:bg-caution/10',
    abnormal: 'bg-abnormal-soft dark:bg-abnormal/10',
    critical: 'bg-critical-soft dark:bg-critical/10',
    brand: 'bg-brand-soft dark:bg-brand/10',
    accent: 'bg-brand-soft dark:bg-brand/10',
    info: 'bg-brand-soft dark:bg-brand/10',
  }
  return (
    <div
      className={cx(
        'flex flex-wrap items-start justify-between gap-3 rounded-[var(--radius)] px-4 py-3.5',
        surfaces[tone],
        className,
      )}
    >
      <div className="min-w-0">
        {title && (
          <p className="text-[13px] font-semibold text-ink">{title}</p>
        )}
        {children && <div className="text-[12.5px] text-ink-muted">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

/** A monospace reference — an order number, a key prefix, a provider id. */
export function Mono({ children }: { children: ReactNode }) {
  return <code className="id text-ink-muted">{children}</code>
}
