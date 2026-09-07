import { Head, Link } from '@inertiajs/react'
import { PageHeader } from '@/views/ui/kit'
import { Blocks, type DocPage } from '@/views/ui/docs'
import { Contents, DocsShell, type DocsNav } from '@/views/ui/DocsShell'
import { IconChevronRight } from '@/views/ui/icons'

export default function DocPageView({
  navigation,
  doc,
  previous,
  next,
  contents,
}: {
  navigation: DocsNav
  doc: DocPage
  previous: { slug: string; title: string } | null
  next: { slug: string; title: string } | null
  contents: { text: string; id: string }[]
}) {
  return (
    <>
      <Head title={doc.title} />
      <PageHeader
        breadcrumbs={[{ label: 'Documentation', href: '/docs' }]}
        title={doc.title}
        subtitle={doc.summary}
      />

      <DocsShell navigation={navigation} aside={<Contents items={contents} />}>
        <article className="max-w-[46rem]">
          <Blocks blocks={doc.blocks} />

          <nav className="mt-10 grid gap-3 border-t border-line pt-6 sm:grid-cols-2">
            {previous ? (
              <Link href={`/docs/${previous.slug}`} className="surface group p-3.5">
                <span className="eyebrow">Previous</span>
                <span className="mt-1 flex items-center gap-1.5 text-[13.5px] font-medium text-ink group-hover:text-brand">
                  <IconChevronRight className="h-3.5 w-3.5 rotate-180" />
                  {previous.title}
                </span>
              </Link>
            ) : (
              <span />
            )}
            {next && (
              <Link href={`/docs/${next.slug}`} className="surface group p-3.5 sm:text-right">
                <span className="eyebrow">Next</span>
                <span className="mt-1 flex items-center gap-1.5 text-[13.5px] font-medium text-ink group-hover:text-brand sm:justify-end">
                  {next.title}
                  <IconChevronRight className="h-3.5 w-3.5" />
                </span>
              </Link>
            )}
          </nav>
        </article>
      </DocsShell>
    </>
  )
}
