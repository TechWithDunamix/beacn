import { Head, Link } from '@inertiajs/react'
import { PageHeader } from '@/views/ui/kit'
import { DocsShell, type DocsNav } from '@/views/ui/DocsShell'

export default function DocsIndex({ navigation, total }: { navigation: DocsNav; total: number }) {
  return (
    <>
      <Head title="Documentation" />
      <PageHeader
        title="Documentation"
        subtitle={`${total} pages — the event model, the realtime protocol, the SDKs, and running BEACN in production.`}
      />

      <DocsShell navigation={navigation}>
        <div className="space-y-8">
          {navigation.map((section) => (
            <section key={section.key}>
              <h2 className="mb-3 text-[15px] font-semibold tracking-[-0.01em] text-ink">
                {section.label}
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {section.pages.map((page) => (
                  <Link
                    key={page.slug}
                    href={`/docs/${page.slug}`}
                    className="surface group p-4 transition hover:border-brand/40"
                  >
                    <p className="text-[13.5px] font-semibold text-ink group-hover:text-brand">
                      {page.title}
                    </p>
                    <p className="mt-1 text-[12.5px] leading-[1.55] text-ink-muted">{page.summary}</p>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      </DocsShell>
    </>
  )
}
