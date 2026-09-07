/**
 * Shared hooks and formatters.
 *
 * The formatters are here rather than in components because a latency has to
 * read the same on a stat tile, in a table cell and in a tooltip. Three
 * spellings of "1.82s" on one screen is how a dashboard stops being trusted.
 */

import { usePage } from '@inertiajs/react'
import { useEffect, useState } from 'react'
import type { SharedProps } from './types'

export function useShared(): SharedProps {
  return usePage().props as unknown as SharedProps
}

export function useAuth() {
  return useShared().auth
}

/**
 * Whether the signed-in user holds a permission.
 *
 * Cosmetic, and worth stating plainly: this hides controls that would refuse.
 * The gate that actually stops an action is on the route, server-side. A page
 * that only hid the button would be a page anyone could POST to.
 */
export function useCan(): (permission: string) => boolean {
  const { permissions } = useAuth()
  return (permission: string) => permissions.includes(permission)
}

/* -- formatters --------------------------------------------------------- */

/** `1,482,309`. */
export function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('en-US')
}

/** `1.4M` — for a stat tile where the exact figure would not fit. */
export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const abs = Math.abs(value)
  if (abs < 1000) return String(Math.round(value))
  if (abs < 1_000_000) return `${(value / 1000).toFixed(abs < 10_000 ? 1 : 0)}K`
  if (abs < 1_000_000_000) return `${(value / 1_000_000).toFixed(abs < 10_000_000 ? 1 : 0)}M`
  return `${(value / 1_000_000_000).toFixed(1)}B`
}

/**
 * `12.4%`.
 *
 * Takes a *fraction*, because every rate the API sends is one. Passing 12.4
 * here and getting "1240%" is the mistake this signature exists to make
 * obvious.
 */
export function percent(value: number | null | undefined, places = 2): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(places)}%`
}

/**
 * `940ms`, `1.82s`.
 *
 * The switch at one second is the one an operator reads by: below it,
 * milliseconds are the unit people say out loud; above it, seconds are.
 */
export function latency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1) return '<1ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

/** `4.2 MB`. Binary units, because that is what a transfer figure means. */
export function bytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let n = value
  let unit = 0
  while (Math.abs(n) >= 1024 && unit < units.length - 1) {
    n /= 1024
    unit += 1
  }
  return `${n.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

/** `12.4/s`. */
export function rate(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${value < 10 ? value.toFixed(2) : Math.round(value).toLocaleString('en-US')}/s`
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function clock(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

/** `4m ago`. Relative, because "is this recent" is the only question asked. */
export function ago(value: string | null | undefined): string {
  if (!value) return 'never'
  const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000)
  if (seconds < 45) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`
  return dateTime(value)
}

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

/* -- behaviour ---------------------------------------------------------- */

export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export function useShortcut(key: string, handler: () => void, withMeta = true): void {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const meta = event.metaKey || event.ctrlKey
      if (event.key.toLowerCase() === key.toLowerCase() && (!withMeta || meta)) {
        event.preventDefault()
        handler()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [key, handler, withMeta])
}

export type Theme = 'light' | 'dark' | 'system'

function prefersDark(): boolean {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return false
  }
}

/**
 * The theme, persisted and applied to the root element.
 *
 * `system` removes the attribute entirely rather than writing a value, which
 * is what lets the CSS fall through to `prefers-color-scheme`. Writing
 * `data-theme="system"` would match neither selector and leave the page in
 * whatever the light tokens say.
 *
 * The third tuple element is the *resolved* theme — `system` collapsed to the
 * mode actually on screen — so a toggle can show the right icon and flip to
 * the opposite of what the reader is looking at, even on first use.
 */
export function useTheme(): [Theme, (next: Theme) => void, 'light' | 'dark'] {
  const [theme, setThemeState] = useState<Theme>(() => {
    try {
      const stored = localStorage.getItem('beacn-theme')
      if (stored === 'dark' || stored === 'light') return stored
    } catch {
      // Private windows and blocked site data throw on access rather than
      // returning null, so the read itself has to be guarded.
    }
    return 'system'
  })

  const [systemDark, setSystemDark] = useState<boolean>(prefersDark)

  // Follow the OS preference while the theme is `system`, so the resolved
  // value and the toggle's icon stay honest without a reload.
  useEffect(() => {
    let media: MediaQueryList
    try {
      media = window.matchMedia('(prefers-color-scheme: dark)')
    } catch {
      return
    }
    const onChange = () => setSystemDark(media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  // Keep the root element in step with state. The inline script in the root
  // template applies a stored `dark`/`light` before first paint; this covers
  // what it cannot — a `system` choice, a change made without a reload, and a
  // reload where state and attribute drifted apart.
  useEffect(() => {
    if (theme === 'system') delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = theme
  }, [theme])

  const setTheme = (next: Theme) => {
    setThemeState(next)
    try {
      if (next === 'system') localStorage.removeItem('beacn-theme')
      else localStorage.setItem('beacn-theme', next)
    } catch {
      /* Nothing to do: the theme still applies for this page view. */
    }
  }

  const resolved: 'light' | 'dark' =
    theme === 'system' ? (systemDark ? 'dark' : 'light') : theme

  return [theme, setTheme, resolved]
}

/** Copy to clipboard, reporting whether it worked so the UI can confirm. */
export function useCopy(): [boolean, (text: string) => void] {
  const [copied, setCopied] = useState(false)
  const copy = (text: string) => {
    navigator.clipboard
      ?.writeText(text)
      .then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1800)
      })
      .catch(() => setCopied(false))
  }
  return [copied, copy]
}
