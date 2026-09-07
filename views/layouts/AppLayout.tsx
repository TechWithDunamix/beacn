/**
 * The control-plane shell: a sidebar, a thin top bar, the page.
 *
 * Same vocabulary as JANUS's shell — a fixed rail with its own scroll, a 14px
 * top bar, permission-filtered navigation, a theme toggle and an account menu.
 * The one BEACN-specific piece is the **environment picker** in the top bar:
 * every number on every screen is scoped to one of development / staging /
 * production, so the selected environment is chrome, not a page control.
 */

import { Link, router, usePage } from '@inertiajs/react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { cx, useCan, useShared, useTheme } from '@/js/hooks'
import { FlashMessages } from '@/views/ui/FlashMessages'
import { Wordmark } from '@/views/ui/Logo'
import { MenuItem, Popover } from '@/views/ui/kit'
import {
  IconAudit,
  IconBook,
  IconChevronDown,
  IconKey,
  IconLogout,
  IconMoon,
  IconOverview,
  IconProducer,
  IconPulse,
  IconSettings,
  IconStream,
  IconSun,
  IconTask,
  IconTopic,
  IconUsers,
  IconBell,
} from '@/views/ui/icons'

type NavItem = {
  label: string
  href: string
  icon: (p: { className?: string }) => ReactNode
  permission?: string
  exact?: boolean
}
type NavGroup = { heading?: string; items: NavItem[] }

const NAVIGATION: NavGroup[] = [
  {
    items: [{ label: 'Dashboard', href: '/', icon: IconOverview, exact: true, permission: 'settings.read' }],
  },
  {
    heading: 'Events',
    items: [
      { label: 'Explorer', href: '/events', icon: IconPulse, permission: 'events.read' },
      { label: 'Topics', href: '/topics', icon: IconTopic, permission: 'topics.read' },
      { label: 'Connections', href: '/connections', icon: IconStream, permission: 'connections.read' },
    ],
  },
  {
    heading: 'Activity',
    items: [
      { label: 'Tasks', href: '/tasks', icon: IconTask, permission: 'tasks.read' },
      { label: 'Notifications', href: '/notifications', icon: IconBell, permission: 'notifications.read' },
    ],
  },
  {
    heading: 'Platform',
    items: [
      { label: 'Producers', href: '/producers', icon: IconProducer, permission: 'producers.read' },
      { label: 'API keys', href: '/api-keys', icon: IconKey, permission: 'apikeys.read' },
      { label: 'Operators', href: '/users', icon: IconUsers, permission: 'users.read' },
      { label: 'Audit log', href: '/audit', icon: IconAudit, permission: 'audit.read' },
      { label: 'Settings', href: '/settings', icon: IconSettings, permission: 'settings.read' },
      // No permission: documentation a ReadOnly operator cannot open is
      // documentation withheld from the person most likely to need it.
      { label: 'Documentation', href: '/docs', icon: IconBook },
    ],
  },
]

function currentEnv(url: string, fallback: string): string {
  const q = new URLSearchParams(url.split('?')[1] ?? '')
  return q.get('env') ?? fallback
}

export function AppLayout({ children }: { children: ReactNode }) {
  const { url } = usePage()
  const { auth, app } = useShared()
  const can = useCan()
  const [, setTheme, resolvedTheme] = useTheme()
  const [mobileOpen, setMobileOpen] = useState(false)

  const path = url.split('?')[0]
  const env = currentEnv(url, app.environments?.[0] ?? 'development')
  const isCurrent = (item: NavItem) =>
    item.exact ? path === item.href : path === item.href || path.startsWith(`${item.href}/`)

  const withEnv = (href: string) => (env && env !== 'development' ? `${href}?env=${env}` : href)

  const groups = NAVIGATION.map((g) => ({
    ...g,
    items: g.items.filter((i) => !i.permission || can(i.permission)),
  })).filter((g) => g.items.length > 0)

  const switchEnv = (next: string) => {
    const target = path === '/' ? '/' : path
    router.get(target, next === 'development' ? {} : { env: next }, { preserveState: false })
  }

  return (
    <div className="min-h-screen bg-canvas text-[13px] text-ink">
      <div className="flex min-h-screen">
        <aside
          className={cx(
            'fixed inset-y-0 left-0 z-40 flex w-[236px] shrink-0 flex-col border-r border-line bg-surface transition-transform',
            'lg:sticky lg:top-0 lg:h-screen lg:translate-x-0',
            mobileOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <div className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-4">
            <Wordmark className="text-[14px]" />
          </div>
          <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
            {groups.map((group, index) => (
              <div key={group.heading ?? index} className={index > 0 ? 'mt-5' : ''}>
                {group.heading && <p className="nav-heading">{group.heading}</p>}
                <div className="mt-1 space-y-0.5">
                  {group.items.map((item) => {
                    const Icon = item.icon
                    return (
                      <Link
                        key={item.href}
                        href={withEnv(item.href)}
                        data-active={isCurrent(item)}
                        className="nav-link"
                      >
                        <Icon className="h-4 w-4" />
                        {item.label}
                      </Link>
                    )
                  })}
                </div>
              </div>
            ))}
          </nav>
          <div className="shrink-0 border-t border-line px-3 py-3 text-[11px] text-ink-faint">
            bus: <span className="mono">{app.bus}</span>
          </div>
        </aside>

        {mobileOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/20 lg:hidden"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-canvas/90 px-4 backdrop-blur lg:px-6">
            <button
              type="button"
              className="rounded-md p-1.5 text-ink-muted hover:bg-sunken lg:hidden"
              onClick={() => setMobileOpen((v) => !v)}
              aria-label="Toggle navigation"
            >
              <span className="block h-0.5 w-4 bg-current" />
              <span className="mt-1 block h-0.5 w-4 bg-current" />
              <span className="mt-1 block h-0.5 w-4 bg-current" />
            </button>

            <Popover
              align="left"
              trigger={({ toggle }) => (
                <button
                  type="button"
                  onClick={toggle}
                  className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-[12px] font-medium text-ink hover:bg-sunken"
                >
                  <span className="dot bg-brand" />
                  {env}
                  <IconChevronDown className="h-3.5 w-3.5 text-ink-faint" />
                </button>
              )}
            >
              {({ close }) => (
                <>
                  {(app.environments ?? ['development']).map((name) => (
                    <MenuItem
                      key={name}
                      onClick={() => {
                        close()
                        switchEnv(name)
                      }}
                    >
                      {name}
                    </MenuItem>
                  ))}
                </>
              )}
            </Popover>

            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
                className="rounded-full p-2 text-ink-muted transition hover:bg-sunken hover:text-ink"
                aria-label="Toggle theme"
              >
                {resolvedTheme === 'dark' ? <IconSun className="h-4 w-4" /> : <IconMoon className="h-4 w-4" />}
              </button>

              <Popover
                trigger={({ toggle }) => (
                  <button
                    type="button"
                    onClick={toggle}
                    className="inline-flex items-center gap-2 rounded-full py-1 pl-1 pr-2.5 text-[12px] font-medium text-ink hover:bg-sunken"
                  >
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-soft text-[11px] font-semibold text-brand">
                      {(auth.user?.name ?? '?').slice(0, 1).toUpperCase()}
                    </span>
                    <span className="hidden sm:inline">{auth.user?.name}</span>
                    <IconChevronDown className="h-3.5 w-3.5 text-ink-faint" />
                  </button>
                )}
              >
                {() => (
                  <>
                    <div className="px-3 py-2 text-[12px]">
                      <div className="font-medium text-ink">{auth.user?.email}</div>
                      <div className="text-ink-faint">{auth.roles.join(', ') || 'no role'}</div>
                    </div>
                    <div className="my-1 border-t border-line" />
                    <MenuItem icon={<IconLogout className="h-4 w-4" />} onClick={() => router.post('/logout')}>
                      Sign out
                    </MenuItem>
                  </>
                )}
              </Popover>
            </div>
          </header>

          <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 lg:px-8 lg:py-8">
            <FlashMessages />
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
