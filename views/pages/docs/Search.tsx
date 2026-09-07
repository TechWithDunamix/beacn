import { Head, Link } from '@inertiajs/react'
import { Empty, PageHeader } from '@/views/ui/kit'
import { DocsShell, type DocsNav } from '@/views/ui/DocsShell'

export default function DocsSearch({
  navigation,
  query,
  results,
}: {
  navigation: DocsNav
  query: string
  results: { slug: string; title: string; summary: string }[]
}) {
  return (
    <>
      <Head title={query ? `Search — ${query}` : 'Search'} />
      <PageHeader
        breadcrumbs={[{ label: 'Documentation', href: '/docs' }]}
        title="Search"
        subtitle={
          query ? `${results.length} page(s) matching “${query}”` : 'Type at least two characters.'
        }
      />

      <DocsShell navigation={navigation}>
        {results.length === 0 ? (
          <div className="surface">
            <Empty
              title={query ? 'Nothing matched' : 'Search the documentation'}
              body={
                query
                  ? 'Try a broader term — the search matches titles, summaries and body text.'
                  : 'Substring search over every page.'
              }
            />
          </div>
        ) : (
          <ul className="space-y-3">
            {results.map((result) => (
              <li key={result.slug}>
                <Link href={`/docs/${result.slug}`} className="surface group block p-4">
                  <p className="text-[13.5px] font-semibold text-ink group-hover:text-brand">
                    {result.title}
                  </p>
                  <p className="mt-1 text-[12.5px] leading-[1.55] text-ink-muted">{result.summary}</p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </DocsShell>
    </>
  )
}
