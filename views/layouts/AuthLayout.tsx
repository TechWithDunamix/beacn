/**
 * The shell for the sign-in screen.
 *
 * Deliberately bare: one centred card on the canvas, the wordmark above it, and
 * nothing else. There is no navigation to show, and a marketing panel beside a
 * login form on an internal control plane is decoration nobody asked for.
 */

import type { ReactNode } from 'react'
import { Wordmark } from '@/views/ui/Logo'

export function AuthLayout({ children, caption }: { children: ReactNode; caption?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas px-4 py-12">
      <div className="w-full max-w-[380px]">
        <div className="mb-8 flex flex-col items-center gap-2.5">
          <Wordmark className="h-7" />
          {caption && <p className="text-[12.5px] text-ink-faint">{caption}</p>}
        </div>
        {children}
      </div>
      <p className="mt-8 text-[11px] text-ink-faint">
        BEACN — realtime event infrastructure
      </p>
    </div>
  )
}
