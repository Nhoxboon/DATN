import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { AuthField } from '../components/auth/AuthField'
import { AuthShell } from '../components/auth/AuthShell'
import { OAuthButton } from '../components/auth/OAuthButton'
import { Button } from '../components/shared/Button'
import { getAuthErrorMessage } from '../services/authService'
import { useAuth } from '../hooks/useAuth'

export function SignUpPage() {
  const navigate = useNavigate()
  const { signUp, signInWithGoogle } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setNotice(null)

    if (password.length < 6) {
      setError('Password must be at least 6 characters.')
      return
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setSubmitting(true)

    try {
      const result = await signUp(email.trim(), password)

      if (result.session) {
        navigate('/dashboard', { replace: true })
        return
      }

      setNotice('Check your email to confirm your account before signing in.')
    } catch (authError) {
      setError(getAuthErrorMessage(authError))
    } finally {
      setSubmitting(false)
    }
  }

  const handleGoogleSignUp = async () => {
    setError(null)
    setNotice(null)
    setGoogleLoading(true)

    try {
      await signInWithGoogle()
    } catch (authError) {
      setError(getAuthErrorMessage(authError))
      setGoogleLoading(false)
    }
  }

  return (
    <AuthShell
      eyebrow="The Digital Atelier"
      title="Create Account"
      description="Begin your journey in the atelier."
      footerPrompt={
        <span>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary hover:text-primary-deep">
            Sign in
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
        <AuthField
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          disabled={submitting || googleLoading}
        />
        <AuthField
          label="Confirm Password"
          type="password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          autoComplete="new-password"
          disabled={submitting || googleLoading}
        />
        <Button type="submit" className="w-full justify-center" disabled={submitting || googleLoading}>
          {submitting ? 'Creating account...' : 'Sign Up'}
        </Button>
        <div className="flex items-center gap-4 py-2 text-sm text-muted">
          <div className="h-px flex-1 bg-outline/40" />
          <span>or continue with</span>
          <div className="h-px flex-1 bg-outline/40" />
        </div>
        <OAuthButton
          label={googleLoading ? 'Opening Google...' : 'Sign up with Google'}
          onClick={handleGoogleSignUp}
          disabled={submitting || googleLoading}
        />
      </form>
    </AuthShell>
  )
}
