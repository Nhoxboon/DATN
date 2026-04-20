import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { AuthField } from '../components/auth/AuthField'
import { AuthShell } from '../components/auth/AuthShell'
import { Button } from '../components/shared/Button'

export function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    navigate('/login')
  }

  return (
    <AuthShell
      title="Forgot password"
      description="Enter your email to reset your password. We&apos;ll send a secure link to your inbox to help you get back to your studio."
      asideTitle="Reset the studio key."
      asideDescription="Account recovery stays quiet and secure. We keep the flow editorial: minimal friction, clear next steps, no visual noise."
    >
      <form className="space-y-5" onSubmit={handleSubmit} noValidate>
        <AuthField label="Email address" type="email" value={email} onChange={setEmail} />
        <Button type="submit" className="w-full justify-center">
          Send Reset Link
        </Button>
        <Link to="/login" className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-deep">
          <ArrowLeft className="h-4 w-4" />
          Back to Login
        </Link>
        <div className="inline-flex items-center gap-2 rounded-full bg-[rgba(0,91,192,0.08)] px-4 py-2 text-sm text-muted">
          <ShieldCheck className="h-4 w-4 text-primary" />
          Secure recovery link
        </div>
      </form>
    </AuthShell>
  )
}
