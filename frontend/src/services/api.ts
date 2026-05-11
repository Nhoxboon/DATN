import { supabase } from '../lib/supabase'

export async function withDelay<T>(value: T, ms = 250): Promise<T> {
  await new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })

  return value
}

export function backendUrl() {
  return (import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '')
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession()

  if (error) {
    throw error
  }

  if (!session?.access_token) {
    throw new Error('You must be signed in to continue.')
  }

  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${session.access_token}`)

  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${backendUrl()}${path}`, {
    ...init,
    headers,
  })

  if (response.status === 204) {
    return undefined as T
  }

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new Error(data.detail || `Request failed with status ${response.status}`)
  }

  return data as T
}
