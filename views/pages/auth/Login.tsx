/**
 * Sign in.
 *
 * One card, three fields, no marketing. The error is deliberately vague — the
 * server answers every failure mode with the same sentence, because saying "no
 * such account" turns the front page of the control plane into a way to test
 * whether an address is registered.
 */

import { Head, useForm, usePage } from '@inertiajs/react'
import { Button, Field, Input, Panel } from '@/views/ui/kit'

export default function Login({ app_name }: { app_name: string }) {
  const { errors } = usePage().props as { errors?: Record<string, string> }
  const form = useForm({ email: '', password: '' })

  return (
    <>
      <Head title="Sign in" />
      <Panel>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            form.post('/login')
          }}
        >
          <div>
            <h1 className="text-[15px] font-semibold tracking-tight">Sign in to {app_name}</h1>
            <p className="mt-1 text-[12.5px] text-ink-muted">
              Use the account an administrator created for you.
            </p>
          </div>

          {errors?.email && (
            <div className="rounded-md border border-critical/30 bg-critical-soft px-3 py-2 text-[12.5px] text-critical">
              {errors.email}
            </div>
          )}

          <Field label="Email">
            <Input
              type="email"
              name="email"
              autoComplete="username"
              autoFocus
              required
              value={form.data.email}
              onChange={(event) => form.setData('email', event.target.value)}
            />
          </Field>

          <Field label="Password">
            <Input
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={form.data.password}
              onChange={(event) => form.setData('password', event.target.value)}
            />
          </Field>

          <Button type="submit" variant="primary" className="w-full" loading={form.processing}>
            Sign in
          </Button>
        </form>
      </Panel>

      <p className="mt-4 text-center text-[11.5px] text-ink-faint">
        Command line: <span className="mono">beacn login</span>
      </p>
    </>
  )
}
