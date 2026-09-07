/**
 * The client entry.
 *
 * Resolves a page component by the name the server sent and wraps it in chrome
 * chosen here, so a new screen cannot forget to have one:
 *
 * - `auth/*`, `errors/*` → the bare centred column
 * - anything else        → the control-plane shell
 */

import { createInertiaApp } from '@inertiajs/react'
import type { ComponentType, ReactNode } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import { AppLayout } from '@/views/layouts/AppLayout'
import { AuthLayout } from '@/views/layouts/AuthLayout'
import { DocsLayout } from '@/views/layouts/DocsLayout'
import './app.css'

const APP_NAME = 'BEACN'

type PageModule = {
  default: ComponentType<Record<string, unknown>> & {
    layout?: (children: ReactNode) => ReactNode
  }
}

function chromeFor(name: string): (children: ReactNode) => ReactNode {
  if (name.startsWith('auth/') || name.startsWith('errors/')) {
    return (children) => <AuthLayout>{children}</AuthLayout>
  }
  // Docs are read, not operated — the reading layout, not the dashboard shell.
  if (name.startsWith('docs/')) {
    return (children) => <DocsLayout>{children}</DocsLayout>
  }
  return (children) => <AppLayout>{children}</AppLayout>
}

createInertiaApp({
  id: 'app',
  title: (title) => (title ? `${title} · ${APP_NAME}` : APP_NAME),
  resolve: async (name) => {
    const pages = import.meta.glob<PageModule>('../views/pages/**/*.tsx')
    const loader = pages[`../views/pages/${name}.tsx`]
    if (!loader) {
      throw new Error(
        `No page component for "${name}". Expected views/pages/${name}.tsx — ` +
          `the name comes from the server's render() call.`,
      )
    }
    const page = await loader()
    page.default.layout ??= chromeFor(name)
    return page.default
  },
  setup({ el, App, props }) {
    if (el.hasChildNodes()) hydrateRoot(el, <App {...props} />)
    else createRoot(el).render(<App {...props} />)
  },
  progress: { color: 'oklch(0.55 0.16 250)', delay: 250, showSpinner: false },
})
