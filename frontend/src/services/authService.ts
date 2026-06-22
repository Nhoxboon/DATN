import type { Session, User } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'
import type { UserProfile } from '../types'

export interface AuthResult {
  session: Session | null
  user: User | null
}

function appUrl() {
  const configuredUrl = import.meta.env.VITE_APP_URL || window.location.origin

  return configuredUrl.replace(/\/$/, '')
}

function backendUrl() {
  return (import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '')
}

function authCallbackUrl(nextPath?: string) {
  const url = new URL(`${appUrl()}/auth/callback`)

  if (nextPath?.startsWith('/')) {
    url.searchParams.set('next', nextPath)
  }

  return url.toString()
}

function requireNoError<T>(data: T, error: unknown): T {
  if (error) {
    throw error
  }

  return data
}

export function getAuthErrorMessage(error: unknown) {
  if (error && typeof error === 'object' && 'message' in error) {
    return String(error.message)
  }

  return 'Something went wrong. Please try again.'
}

export function buildUserProfile(user: User | null): UserProfile | null {
  if (!user) {
    return null
  }

  const fullName =
    typeof user.user_metadata.full_name === 'string'
      ? user.user_metadata.full_name
      : typeof user.user_metadata.name === 'string'
        ? user.user_metadata.name
        : user.email?.split('@')[0] || 'Scholar'
  const avatarLabel = fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
    .padEnd(2, 'S')
    .slice(0, 2)

  return {
    id: user.id,
    name: fullName,
    role: user.email || 'Research workspace',
    avatarLabel,
  }
}

export const authService = {
  async getSession(): Promise<Session | null> {
    const { data, error } = await supabase.auth.getSession()

    return requireNoError(data.session, error)
  },

  async signInWithPassword(email: string, password: string): Promise<AuthResult> {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })

    return requireNoError({ session: data.session, user: data.user }, error)
  },

  async signUp(email: string, password: string): Promise<AuthResult> {
    const response = await fetch(`${backendUrl()}/auth/sign-up`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email,
        password,
        email_redirect_to: authCallbackUrl(),
      }),
    })

    const data = (await response.json().catch(() => ({}))) as {
      detail?: string
      session?: { access_token?: string; refresh_token?: string } | null
    }

    if (!response.ok) {
      throw new Error(data.detail || 'Could not create account. Please try again.')
    }

    if (data.session?.access_token && data.session.refresh_token) {
      const { data: sessionData, error } = await supabase.auth.setSession({
        access_token: data.session.access_token,
        refresh_token: data.session.refresh_token,
      })

      return requireNoError(
        { session: sessionData.session, user: sessionData.session?.user ?? null },
        error,
      )
    }

    return { session: null, user: null }
  },

  async signInWithGoogle(nextPath?: string) {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: authCallbackUrl(nextPath),
      },
    })

    return requireNoError(data, error)
  },

  async requestPasswordReset(email: string) {
    const checkResponse = await fetch(`${backendUrl()}/auth/check-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })

    if (!checkResponse.ok) {
      const errorData = (await checkResponse.json().catch(() => ({}))) as { detail?: string }
      throw new Error(errorData.detail || 'Tài khoản không tồn tại')
    }

    const { data, error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${appUrl()}/reset-password`,
    })

    return requireNoError(data, error)
  },

  async exchangeCodeForSession(code: string): Promise<Session | null> {
    const { data, error } = await supabase.auth.exchangeCodeForSession(code)

    return requireNoError(data.session, error)
  },

  async updatePassword(password: string, currentPassword?: string): Promise<User> {
    const { data, error } = await supabase.auth.updateUser({
      password,
      ...(currentPassword ? { current_password: currentPassword } : {}),
    })

    const user = requireNoError(data.user, error)

    if (!user) {
      throw new Error('Password was updated, but the user session could not be refreshed.')
    }

    return user
  },

  async signOut() {
    const { error } = await supabase.auth.signOut()

    requireNoError(null, error)
  },
}
