import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { AuthField } from '../components/auth/AuthField'
import { AuthShell } from '../components/auth/AuthShell'
import { Button } from '../components/shared/Button'
import { getAuthErrorMessage } from '../services/authService'
import { useAuth } from '../hooks/useAuth'

export function ResetPasswordPage() {
  const navigate = useNavigate()
  const { loading, user, updatePassword, signOut } = useAuth()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)

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
      await updatePassword(password)
      await signOut()
      navigate('/login', {
        replace: true,
        state: { message: 'Password updated. Please sign in with your new password.' },
      })
    } catch (authError) {
      setError(getAuthErrorMessage(authError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title="Reset password"
      description="Create a new password from your secure recovery link."
      asideTitle="Reset the studio key."
      asideDescription="Your recovery link opens a temporary authenticated session so the password can be updated safely."
    >
      <form className="space-y-5" onSubmit={handleSubmit} noValidate>
        {!loading && !user && (
          <div className="rounded-[14px] bg-red-50 px-4 py-3 text-sm leading-6 text-red-700">
            This reset link is invalid or expired. Request a new recovery email.
          </div>
        )}
        {error && (
          <div className="rounded-[14px] bg-red-50 px-4 py-3 text-sm leading-6 text-red-700">
            {error}
          </div>
        )}
        <AuthField
          label="New password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          disabled={submitting || loading || !user}
        />
        <AuthField
          label="Confirm new password"
          type="password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          autoComplete="new-password"
          disabled={submitting || loading || !user}
        />
        <Button type="submit" className="w-full justify-center" disabled={submitting || loading || !user}>
          {submitting ? 'Updating...' : 'Update Password'}
        </Button>
        <Link
          to="/forgot-password"
          className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-deep"
        >
          <ArrowLeft className="h-4 w-4" />
          Request a new link
        </Link>
        <div className="inline-flex items-center gap-2 rounded-full bg-[rgba(0,91,192,0.08)] px-4 py-2 text-sm text-muted">
          <ShieldCheck className="h-4 w-4 text-primary" />
          Secure password recovery
        </div>
      </form>
    </AuthShell>
  )
}
