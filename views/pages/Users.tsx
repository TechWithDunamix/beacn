/** Operator accounts — create, assign a role, enable/disable.
 *
 * The create path calls `POST /api/control/users`, which runs the framework's
 * `sillo.users.commands.create_user` / `create_admin` plus BEACN's role
 * assignment — the same code `beacn user create` runs on the CLI.
 */

import { Head, router } from '@inertiajs/react'
import { useState } from 'react'
import { ago, dateTime, useAuth, useCan } from '@/js/hooks'
import { api } from '@/js/api'
import {
  Badge,
  Button,
  Checkbox,
  Empty,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from '@/views/ui/kit'

interface Operator {
  id: number
  email: string
  name: string
  title: string | null
  active: boolean
  superuser: boolean
  roles: string[]
  last_login: string | null
}

interface Props {
  users: Operator[]
  roles: string[]
  role_descriptions: Record<string, string>
  permissions: Record<string, string>
}

export default function Users({ users, roles, role_descriptions }: Props) {
  const can = useCan()
  const me = useAuth().user
  const writable = can('users.write')

  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    email: '',
    password: '',
    role: roles.includes('ReadOnly') ? 'ReadOnly' : roles[0] ?? '',
    superuser: false,
  })

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.post('/users', form)
      setOpen(false)
      setForm({ email: '', password: '', role: form.role, superuser: false })
      router.reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const setRole = async (email: string, role: string) => {
    await api.post('/users/role', { email, role })
    router.reload()
  }

  const setActive = async (email: string, active: boolean) => {
    await api.post('/users/active', { email, active })
    router.reload()
  }

  return (
    <>
      <Head title="Operators" />
      <PageHeader
        title="Operators"
        subtitle={`${users.filter((u) => u.active).length} active · roles: ${roles.join(', ')}`}
        actions={writable && <Button variant="primary" onClick={() => setOpen(true)}>Add operator</Button>}
      />

      {users.length === 0 ? (
        <Empty
          title="No operators"
          body="Create the first account with the CLI — beacn user create you@example.com --role Admin --admin — or add one here."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Operator</TH>
              <TH>Role</TH>
              <TH>Status</TH>
              <TH align="right">Last sign-in</TH>
              <TH align="right" />
            </TR>
          </THead>
          <TBody>
            {users.map((u) => {
              const isMe = me?.id === u.id
              return (
                <TR key={u.id}>
                  <TD>
                    <div className="font-medium text-ink">
                      {u.name}
                      {u.superuser && <Badge tone="brand">superuser</Badge>}
                      {isMe && <span className="ml-2 text-[11px] text-ink-faint">you</span>}
                    </div>
                    <div className="mono text-[11px] text-ink-faint">{u.email}</div>
                  </TD>
                  <TD>
                    {writable && !u.superuser ? (
                      <Select
                        value={u.roles[0] ?? ''}
                        onChange={(e) => setRole(u.email, e.target.value)}
                        className="h-8 w-40 py-1 text-[12px]"
                      >
                        {roles.map((r) => (
                          <option key={r} value={r} title={role_descriptions[r]}>{r}</option>
                        ))}
                      </Select>
                    ) : (
                      <span>{u.roles.join(', ') || '—'}</span>
                    )}
                  </TD>
                  <TD>
                    <Badge tone={u.active ? 'ok' : 'neutral'} dot>{u.active ? 'active' : 'disabled'}</Badge>
                  </TD>
                  <TD align="right" title={u.last_login ? dateTime(u.last_login) : ''}>
                    {u.last_login ? ago(u.last_login) : 'never'}
                  </TD>
                  <TD align="right">
                    {writable && !isMe && (
                      <Button
                        size="xs"
                        variant={u.active ? 'danger' : 'secondary'}
                        onClick={() => setActive(u.email, !u.active)}
                      >
                        {u.active ? 'Disable' : 'Enable'}
                      </Button>
                    )}
                  </TD>
                </TR>
              )
            })}
          </TBody>
        </Table>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Add operator"
        description="Creates a control-plane login and assigns a role."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={!form.email || form.password.length < 10}
              onClick={create}
            >
              Create
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {error && <p className="text-[12px] text-critical">{error}</p>}
          <Field label="Email" required>
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="teammate@example.com"
            />
          </Field>
          <Field label="Password" required hint="At least 10 characters. A superuser also passes the framework password policy.">
            <Input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </Field>
          <Field label="Role">
            <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {roles.map((r) => (
                <option key={r} value={r}>
                  {r} — {role_descriptions[r]}
                </option>
              ))}
            </Select>
          </Field>
          <Checkbox
            label="Superuser (Owner escape hatch)"
            hint="Holds every permission regardless of role. Use sparingly."
            checked={form.superuser}
            onChange={(e) => setForm({ ...form, superuser: e.target.checked })}
          />
        </div>
      </Modal>
    </>
  )
}
