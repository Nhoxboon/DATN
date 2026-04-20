import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { AuthField } from '../components/auth/AuthField'
import { AuthShell } from '../components/auth/AuthShell'
import { OAuthButton } from '../components/auth/OAuthButton'
import { Button } from '../components/shared/Button'

export function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    navigate('/dashboard')
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
        <AuthField label="Email Address" type="email" value={email} onChange={setEmail} />
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm font-medium text-ink">
            <span>Password</span>
            <Link to="/forgot-password" className="text-primary hover:text-primary-deep">
              Forgot password?
            </Link>
          </div>
          <AuthField label="" type="password" value={password} onChange={setPassword} />
        </div>
        <Button type="submit" className="w-full justify-center">
          Sign In
        </Button>
        <div className="flex items-center gap-4 py-2 text-sm text-muted">
          <div className="h-px flex-1 bg-outline/40" />
          <span>or continue with</span>
          <div className="h-px flex-1 bg-outline/40" />
        </div>
        <OAuthButton label="Sign in with Google" />
      </form>
    </AuthShell>
  )
}
