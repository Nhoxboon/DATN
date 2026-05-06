import { createContext } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import type { AuthResult } from '../services/authService'

export interface AuthContextValue {
  session: Session | null
  user: User | null
  loading: boolean
  isPasswordRecovery: boolean
  signInWithPassword: (email: string, password: string) => Promise<AuthResult>
  signUp: (email: string, password: string) => Promise<AuthResult>
  signInWithGoogle: (nextPath?: string) => Promise<void>
  requestPasswordReset: (email: string) => Promise<void>
  updatePassword: (password: string, currentPassword?: string) => Promise<User>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
