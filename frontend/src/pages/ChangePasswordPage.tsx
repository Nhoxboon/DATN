import { ArrowLeft, BookOpenText, KeyRound, WandSparkles } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { AuthField } from '../components/auth/AuthField'
import { Button } from '../components/shared/Button'
import { getAuthErrorMessage } from '../services/authService'
import { useAuth } from '../hooks/useAuth'

export function ChangePasswordPage() {
  const navigate = useNavigate()
  const { updatePassword } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setNotice(null)

    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters.')
      return
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setSubmitting(true)

    try {
      await updatePassword(newPassword, currentPassword)
      setNotice('Password updated successfully.')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      window.setTimeout(() => navigate('/dashboard'), 900)
    } catch (authError) {
      setError(getAuthErrorMessage(authError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4 py-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(0,91,192,0.08),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(112,68,193,0.06),transparent_24%),radial-gradient(circle_at_top_right,rgba(43,52,55,0.05),transparent_18%)]" />
      <BookOpenText className="pointer-events-none absolute bottom-8 left-8 h-12 w-12 -rotate-12 text-ink/20" />
      <WandSparkles className="pointer-events-none absolute right-8 top-8 h-12 w-12 rotate-18 text-ink/16" />

      <div className="relative z-10 flex w-full max-w-135 flex-col items-center">
        <div className="mb-8 flex flex-col items-center gap-2.5">
          <span className="flex h-12 w-12 items-center justify-center rounded-[10px] bg-linear-to-br from-primary to-primary-deep text-white shadow-paper">
            <KeyRound className="h-5.5 w-5.5" />
          </span>
          <span className="font-display text-[0.68rem] uppercase tracking-[0.24em] text-ink">
            Scholar Script
          </span>
        </div>

        <div className="w-full rounded-[18px] bg-white px-8 py-8 shadow-[0_18px_48px_rgba(43,52,55,0.12)] sm:px-10 sm:py-9">
          <div className="mb-4 space-y-2.5">
            <h1 className="text-[2rem] font-semibold tracking-[-0.03em] text-ink">Change Password</h1>
            <p className="max-w-90 text-[0.86rem] leading-6 text-muted">
              Ensure your account remains secure by using a strong password.
            </p>
          </div>

          <form className="flex flex-col pt-0" onSubmit={handleSubmit} noValidate>
            {notice && (
              <div className="mb-5 rounded-[14px] bg-[rgba(0,91,192,0.08)] px-4 py-3 text-sm leading-6 text-primary">
                {notice}
              </div>
            )}
            {error && (
              <div className="mb-5 rounded-[14px] bg-red-50 px-4 py-3 text-sm leading-6 text-red-700">
                {error}
              </div>
            )}
            <div className="flex flex-col" style={{ gap: '1.25rem' }}>
              <AuthField
                label="Current Password"
                type="password"
                placeholder="Enter your current password"
                value={currentPassword}
                onChange={setCurrentPassword}
                autoComplete="current-password"
                disabled={submitting}
              />

              <AuthField
                label="New Password"
                type="password"
                placeholder="Enter your new password"
                value={newPassword}
                onChange={setNewPassword}
                autoComplete="new-password"
                disabled={submitting}
              />

              <AuthField
                label="Confirm New Password"
                type="password"
                placeholder="Repeat your new password"
                value={confirmPassword}
                onChange={setConfirmPassword}
                autoComplete="new-password"
                disabled={submitting}
              />
            </div>

            <Button type="submit" className="mt-8 h-11 w-full justify-center rounded-lg" disabled={submitting}>
              {submitting ? 'Updating...' : 'Update Password'}
            </Button>
          </form>

          <div className="mt-6 text-center">
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-2 text-[0.72rem] font-medium text-primary hover:text-primary-deep"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to Dashboard
            </Link>
          </div>
        </div>

        <p className="mt-7 text-center text-[0.62rem] text-muted">
          © 2024 Scholar Script Atelier. All intellectual property reserved.
        </p>
      </div>
    </main>
  )
}
