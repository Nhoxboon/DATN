import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { AuthField } from '../components/auth/AuthField'
import { AuthShell } from '../components/auth/AuthShell'
import { OAuthButton } from '../components/auth/OAuthButton'
import { Button } from '../components/shared/Button'

export function SignUpPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    navigate('/dashboard')
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
        <AuthField label="Email Address" type="email" value={email} onChange={setEmail} />
        <AuthField label="Password" type="password" value={password} onChange={setPassword} />
        <AuthField
          label="Confirm Password"
          type="password"
          value={confirmPassword}
          onChange={setConfirmPassword}
        />
        <Button type="submit" className="w-full justify-center">
          Sign Up
        </Button>
        <div className="flex items-center gap-4 py-2 text-sm text-muted">
          <div className="h-px flex-1 bg-outline/40" />
          <span>or continue with</span>
          <div className="h-px flex-1 bg-outline/40" />
        </div>
        <OAuthButton label="Sign up with Google" />
      </form>
    </AuthShell>
  )
}
