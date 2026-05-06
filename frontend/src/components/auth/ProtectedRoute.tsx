import type { PropsWithChildren } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'

export function ProtectedRoute({ children }: PropsWithChildren) {
  const { loading, user } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background text-sm font-medium text-muted">
        Loading workspace...
      </main>
    )
  }

  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ redirectTo: `${location.pathname}${location.search}` }}
      />
    )
  }

  return children
}
