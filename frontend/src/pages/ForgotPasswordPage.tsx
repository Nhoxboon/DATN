import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { AuthField } from '../components/auth/AuthField'
import { AuthShell } from '../components/auth/AuthShell'
import { Button } from '../components/shared/Button'
import { getAuthErrorMessage } from '../services/authService'
import { useAuth } from '../hooks/useAuth'

export function ForgotPasswordPage() {
  const { requestPasswordReset } = useAuth()
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [cooldownSeconds, setCooldownSeconds] = useState(0)

  useEffect(() => {
    if (cooldownSeconds <= 0) {
      return undefined
    }

    const timerId = window.setTimeout(() => {
      setCooldownSeconds((current) => Math.max(current - 1, 0))
    }, 1000)

    return () => window.clearTimeout(timerId)
  }, [cooldownSeconds])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (cooldownSeconds > 0) {
      return
    }

    setError(null)
    setNotice(null)
    setSubmitting(true)

    try {
      await requestPasswordReset(email.trim())
      setNotice('If an account exists for this email, a secure reset link has been sent.')
      setCooldownSeconds(60)
    } catch (authError) {
      setError(getAuthErrorMessage(authError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title="Forgot password"
      description="Enter your email to reset your password. We&apos;ll send a secure link to your inbox to help you get back to your studio."
      asideTitle="Reset the studio key."
      asideDescription="Account recovery stays quiet and secure. We keep the flow editorial: minimal friction, clear next steps, no visual noise."
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
          label="Email address"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          disabled={submitting}
        />
        <Button
          type="submit"
          className="mt-7 w-full justify-center"
          disabled={submitting || cooldownSeconds > 0}
        >
          {submitting
            ? 'Sending...'
            : cooldownSeconds > 0
              ? `Send again in ${cooldownSeconds}s`
              : 'Send Reset Link'}
        </Button>
        <div className="flex flex-col gap-3 pt-1 sm:flex-row sm:items-center sm:justify-between">
          <Link
            to="/login"
            className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-deep"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Login
          </Link>
          <div className="inline-flex items-center gap-2 rounded-full bg-[rgba(0,91,192,0.08)] px-4 py-2 text-sm text-muted">
            <ShieldCheck className="h-4 w-4 text-primary" />
            Secure recovery link
          </div>
        </div>
      </form>
    </AuthShell>
  )
}
