/**
 * api.ts — typed REST client for server/main.py's /api/* routes. Ported
 * from web/app.js's fetchJson + call sites, kept framework-agnostic so
 * useSession.ts (or any future screen) can call it directly.
 */
import type { Clause, Report } from './protocol'

export class ApiError extends Error {}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T | null> {
  const resp = await fetch(url, options)
  let body: unknown = null
  try {
    body = await resp.json()
  } catch {
    /* empty body is fine for some endpoints */
  }
  if (!resp.ok) {
    const detail =
      (body && typeof body === 'object' && 'detail' in body ? String((body as { detail: unknown }).detail) : null) ??
      resp.statusText
    throw new ApiError(detail)
  }
  return body as T | null
}

export async function health(): Promise<{ status: string }> {
  return (await fetchJson<{ status: string }>('/api/health'))!
}

export async function loadDemoContract(): Promise<Clause[]> {
  const body = await fetchJson<{ clauses: Clause[] }>('/api/contract/demo', { method: 'POST' })
  return body!.clauses
}

export async function uploadContract(file: File): Promise<Clause[]> {
  const form = new FormData()
  form.append('file', file)
  const body = await fetchJson<{ clauses: Clause[] }>('/api/contract', { method: 'POST', body: form })
  return body!.clauses
}

export async function getContract(): Promise<Clause[]> {
  const body = await fetchJson<{ clauses: Clause[] }>('/api/contract')
  return body!.clauses
}

export async function setConsent(accepted: boolean): Promise<boolean> {
  const body = await fetchJson<{ consent: boolean }>('/api/consent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accepted }),
  })
  return body!.consent
}

export async function startSession(): Promise<string> {
  const body = await fetchJson<{ session_id: string }>('/api/session/start', { method: 'POST' })
  return body!.session_id
}

export async function endSession(sessionId: string): Promise<Report> {
  return (await fetchJson<Report>(`/api/session/${sessionId}/end`, { method: 'POST' }))!
}

export async function getReport(sessionId: string): Promise<Report> {
  return (await fetchJson<Report>(`/api/session/${sessionId}/report`))!
}
