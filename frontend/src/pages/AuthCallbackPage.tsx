import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authService, getAuthErrorMessage } from '../services/authService'

export function AuthCallbackPage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function finishAuth() {
      try {
        const params = new URLSearchParams(window.location.search)
        const code = params.get('code')
        const nextPath = params.get('next')

        if (code) {
          await authService.exchangeCodeForSession(code)
        } else {
          await authService.getSession()
        }

        if (!cancelled) {
          navigate(nextPath?.startsWith('/') ? nextPath : '/dashboard', { replace: true })
        }
      } catch (authError) {
        if (!cancelled) {
          setError(getAuthErrorMessage(authError))
        }
      }
    }

    void finishAuth()

    return () => {
      cancelled = true
    }
  }, [navigate])

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-[18px] bg-white px-8 py-8 text-center shadow-[0_18px_48px_rgba(43,52,55,0.12)]">
        <h1 className="font-display text-2xl font-semibold text-ink">
          {error ? 'Authentication failed' : 'Finishing sign in...'}
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          {error || 'We are securely connecting your account to Scholar Script.'}
        </p>
        {error && (
          <Link
            to="/login"
            className="mt-6 inline-flex text-sm font-medium text-primary hover:text-primary-deep"
          >
            Back to login
          </Link>
        )}
      </div>
    </main>
  )
}
