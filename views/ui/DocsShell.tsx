/**
 * The documentation shell: a contents rail, the page, and an on-page outline.
 *
 * Quiet by design — no icons, no active bar, just weight and colour — because
 * it is a second rail inside an app that already has one. It has its own
 * scroll so a long page does not take the contents away with it.
 */

import { Link, router, usePage } from '@inertiajs/react'
import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { cx, useDebounced } from '@/js/hooks'
import { IconSearch } from './icons'

export type DocsNav = {
  key: string
  label: string
  pages: { slug: string; title: string; summary: string }[]
}[]

export function DocsShell({
  navigation,
  children,
  aside,
}: {
  navigation: DocsNav
  children: ReactNode
  aside?: ReactNode
}) {
  const { url } = usePage()
  const current = url.split('?')[0]

  return (
    <div className="flex gap-8">
      <nav className="sticky top-20 hidden h-[calc(100vh-7rem)] w-[220px] shrink-0 overflow-y-auto lg:block">
        <DocsSearch />
        <div className="mt-5 space-y-6">
          {navigation.map((section) => (
            <div key={section.key}>
              <p className="eyebrow mb-2">{section.label}</p>
              <ul className="space-y-px">
                {section.pages.map((page) => {
                  const active = current === `/docs/${page.slug}`
                  return (
                    <li key={page.slug}>
                      <Link
                        href={`/docs/${page.slug}`}
                        aria-current={active ? 'page' : undefined}
                        className={cx(
                          'block rounded-[var(--radius-sm)] px-2.5 py-1.5 text-[13px] transition',
                          active
                            ? 'bg-brand-soft font-medium text-brand'
                            : 'text-ink-muted hover:bg-sunken hover:text-ink',
                        )}
                      >
                        {page.title}
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>
      </nav>

      <div className="min-w-0 flex-1">{children}</div>

      {aside && <aside className="sticky top-20 hidden h-fit w-[180px] shrink-0 xl:block">{aside}</aside>}
    </div>
  )
}

function DocsSearch() {
  const { url } = usePage()
  const initial = new URLSearchParams(url.split('?')[1] ?? '').get('q') ?? ''
  const [query, setQuery] = useState(initial)
  const debounced = useDebounced(query, 300)

  useEffect(() => {
    if (debounced === initial) return
    if (debounced.trim().length < 2) return
    router.get('/docs/search', { q: debounced }, { preserveState: true, replace: true })
  }, [debounced]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="relative">
      <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search docs"
        aria-label="Search documentation"
        className="ring-focus h-9 w-full rounded-full border border-line bg-surface pl-9 pr-3 text-[13px] text-ink placeholder:text-ink-faint"
      />
    </div>
  )
}

/** The on-page outline, from the page's level-2 headings. */
export function Contents({ items }: { items: { text: string; id: string }[] }) {
  if (items.length < 2) return null
  return (
    <>
      <p className="eyebrow mb-2">On this page</p>
      <ul className="space-y-1.5 border-l border-line">
        {items.map((item) => (
          <li key={item.id}>
            <a
              href={`#${item.id}`}
              className="-ml-px block border-l border-transparent pl-3 text-[12.5px] leading-snug text-ink-muted transition hover:border-brand hover:text-brand"
            >
              {item.text}
            </a>
          </li>
        ))}
      </ul>
    </>
  )
}
