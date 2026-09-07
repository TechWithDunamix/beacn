/**
 * 403.
 *
 * Names the missing permission. A generic "you do not have access" leaves an
 * operator to guess which role to ask for, and the permission string is
 * exactly what they need to put in the request.
 */

import { Head, Link } from '@inertiajs/react'
import { Panel } from '@/views/ui/kit'

export default function Forbidden({ permission }: { permission: string | null }) {
  return (
    <>
      <Head title="Not permitted" />
      <Panel>
        <h1 className="text-[15px] font-semibold">You do not have access to this</h1>
        <p className="mt-2 text-[12.5px] text-ink-muted">
          {permission ? (
            <>
              This screen needs the <span className="mono">{permission}</span> permission, which
              your role does not hold.
            </>
          ) : (
            'Your role does not permit this.'
          )}
        </p>
        <Link href="/" className="mt-4 inline-block text-[12.5px] font-medium text-brand">
          Back to the overview
        </Link>
      </Panel>
    </>
  )
}
