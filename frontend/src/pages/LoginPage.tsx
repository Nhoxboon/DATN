import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { AuthField } from '../components/auth/AuthField'
import { AuthShell } from '../components/auth/AuthShell'
import { OAuthButton } from '../components/auth/OAuthButton'
import { Button } from '../components/shared/Button'
import { getAuthErrorMessage } from '../services/authService'
import { useAuth } from '../hooks/useAuth'

interface LoginLocationState {
  message?: string
  redirectTo?: string
}

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { signInWithPassword, signInWithGoogle } = useAuth()
  const locationState = location.state as LoginLocationState | null
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(locationState?.message ?? null)
  const [submitting, setSubmitting] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setNotice(null)
    setSubmitting(true)

    try {
      await signInWithPassword(email.trim(), password)
      navigate(locationState?.redirectTo || '/dashboard', { replace: true })
    } catch (authError) {
      setError(getAuthErrorMessage(authError))
    } finally {
      setSubmitting(false)
    }
  }

  const handleGoogleSignIn = async () => {
    setError(null)
    setNotice(null)
    setGoogleLoading(true)

    try {
      await signInWithGoogle(locationState?.redirectTo)
    } catch (authError) {
      setError(getAuthErrorMessage(authError))
      setGoogleLoading(false)
    }
  }

  return (
    <AuthShell
      eyebrow="The Digital Atelier"
      title="Scholar Script"
      description="Sign in to resume your research studio and continue shaping your next synthesis."
      asideTitle="The Digital Atelier"
      asideDescription="An editorial workspace for collecting sources, drafting sharp notes, and transforming evidence into presentation-ready insight."
      footerPrompt={
        <span>
          Don&apos;t have an account?{' '}
          <Link to="/sign-up" className="font-medium text-primary hover:text-primary-deep">
            Sign up
          </Link>
        </span>
      }
    >
      <form className="space-y-5" onSubmit={handleSubmit} noValidate>
        {notice && (
          <div className="rounded-[14px] bg-[rgba(0,91,192,0.08)] px-4 py-3 text-sm leading-6 text-primary">
            {notice}
          </div>
        )}
        {error && (
          <div className="rounded-[14px] bg-red-50 px-4 py-3 text-sm leading-6 text-red-700">
            {error}
          </div>
        )}
        <AuthField
          label="Email Address"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          disabled={submitting || googleLoading}
        />
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm font-medium text-ink">
            <span>Password</span>
            <Link to="/forgot-password" className="text-primary hover:text-primary-deep">
              Forgot password?
            </Link>
          </div>
          <AuthField
            label=""
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            disabled={submitting || googleLoading}
          />
        </div>
        <Button type="submit" className="w-full justify-center" disabled={submitting || googleLoading}>
          {submitting ? 'Signing in...' : 'Sign In'}
        </Button>
        <div className="flex items-center gap-4 py-2 text-sm text-muted">
          <div className="h-px flex-1 bg-outline/40" />
          <span>or continue with</span>
          <div className="h-px flex-1 bg-outline/40" />
        </div>
        <OAuthButton
          label={googleLoading ? 'Opening Google...' : 'Sign in with Google'}
          onClick={handleGoogleSignIn}
          disabled={submitting || googleLoading}
        />
      </form>
    </AuthShell>
  )
}
