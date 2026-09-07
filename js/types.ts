/** Shared Inertia props — see `app/inertia.py::share_globals`. */

export interface AuthUser {
  id: number
  name: string
  email: string
  title: string | null
  is_superuser: boolean
}

export interface SharedProps {
  auth: {
    user: AuthUser | null
    permissions: string[]
    roles: string[]
  }
  app: {
    name: string
    env: string
    environments: string[]
    bus: string
  }
  errors?: Record<string, string>
  flash?: { type: string; message: string } | null
  [key: string]: unknown
}

/** The event envelope as a consumer receives it. */
export interface BeacnEvent {
  id: string
  event: string
  topic: string
  kind: 'event' | 'task' | 'notification' | 'message'
  producer: string | null
  environment: string
  timestamp: string
  severity: string
  schema_version: string
  data: Record<string, unknown>
  source?: string
  occurred_at?: string
  correlation_id?: string
  request_id?: string
  user_id?: string
  organization_id?: string
  project_id?: string
  delivery?: { delivered: number; subscribers: number }
}
