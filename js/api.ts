/**
 * The dashboard's client for the control-plane API.
 *
 * Same-origin, cookie-authenticated. Every request carries `X-BEACN-Control`,
 * the header the server requires on a session-authenticated write (a cross-site
 * form cannot set it without a CORS preflight the config does not grant). Read
 * paths send it too, harmlessly, so there is one code path.
 */

export interface ApiError {
  code: string
  message: string
  details?: unknown
}

export class ApiRequestError extends Error {
  code: string
  status: number
  details?: unknown
  constructor(status: number, body: ApiError) {
    super(body.message || `HTTP ${status}`)
    this.name = 'ApiRequestError'
    this.status = status
    this.code = body.code || 'error'
    this.details = body.details
  }
}

function url(path: string, params?: Record<string, unknown>): string {
  const base = path.startsWith('/api/') ? path : `/api/control${path}`
  if (!params) return base
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `${base}?${s}` : base
}

async function request<T>(method: string, path: string, opts: {
  params?: Record<string, unknown>
  body?: unknown
} = {}): Promise<T> {
  const res = await fetch(url(path, opts.params), {
    method,
    credentials: 'same-origin',
    headers: {
      'X-BEACN-Control': '1',
      Accept: 'application/json',
      ...(opts.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })
  const text = await res.text()
  const parsed = text ? JSON.parse(text) : {}
  if (!res.ok) {
    throw new ApiRequestError(res.status, parsed.error ?? { code: 'error', message: text })
  }
  return parsed as T
}

export const api = {
  get: <T,>(path: string, params?: Record<string, unknown>) =>
    request<T>('GET', path, { params }),
  post: <T,>(path: string, body?: unknown) => request<T>('POST', path, { body }),
}
