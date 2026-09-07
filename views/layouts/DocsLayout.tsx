/**
 * The documentation shell — deliberately not the dashboard's.
 *
 * Docs are a different mode of use from operating the platform: you arrive to
 * read, often from a link. Wrapping them in the operational sidebar puts a
 * column of links you are not going to click beside the one thing you came
 * for, and narrows the reading measure. So this is a reading layout: a centred
 * measure, a quiet header, one way back to the dashboard.
 */

import { Link } from '@inertiajs/react'
import type { ReactNode } from 'react'
import { useTheme } from '@/js/hooks'
import { Mark } from '@/views/ui/Logo'
import { IconChevronRight, IconMoon, IconSun } from '@/views/ui/icons'

export function DocsLayout({ children }: { children: ReactNode }) {
  const [, setTheme, resolved] = useTheme()

  return (
    <div className="min-h-screen bg-canvas text-[13px] text-ink-muted">
      <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-[1400px] items-center gap-3 px-4 lg:px-8">
          <Link href="/docs" className="flex items-center gap-2">
            <Mark className="h-[18px] w-[18px] text-brand" />
            <span className="text-[14px] font-semibold tracking-tight text-ink">BEACN</span>
            <span className="text-[13px] text-ink-faint">docs</span>
          </Link>

          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              onClick={() => setTheme(resolved === 'dark' ? 'light' : 'dark')}
              aria-label={resolved === 'dark' ? 'Light theme' : 'Dark theme'}
              className="ring-focus rounded-full p-2 text-ink-faint transition hover:bg-sunken hover:text-ink"
            >
              {resolved === 'dark' ? <IconSun className="h-4 w-4" /> : <IconMoon className="h-4 w-4" />}
            </button>
            <Link
              href="/"
              className="ring-focus ml-1 inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-[12.5px] font-medium text-ink transition hover:bg-sunken"
            >
              Dashboard
              <IconChevronRight className="h-3.5 w-3.5 text-ink-faint" />
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-[1400px] px-4 py-8 lg:px-8">{children}</div>

      <footer className="border-t border-line">
        <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-6 text-[12px] text-ink-faint lg:px-8">
          <span>BEACN — realtime event infrastructure</span>
          <a href="https://sillo.build" target="_blank" rel="noreferrer" className="hover:text-brand">
            Sillo
          </a>
          <Link href="/docs" className="ml-auto hover:text-brand">
            All documentation
          </Link>
        </div>
      </footer>
    </div>
  )
}
