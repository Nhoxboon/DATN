import type { PropsWithChildren } from 'react'
import { useEffect, useMemo, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '../../lib/supabase'
import { authService } from '../../services/authService'
import { AuthContext } from '../../contexts/AuthContext'

export function AuthProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [isPasswordRecovery, setIsPasswordRecovery] = useState(false)

  useEffect(() => {
    let mounted = true

    void authService
      .getSession()
      .then((initialSession) => {
        if (!mounted) {
          return
        }

        setSession(initialSession)
      })
      .finally(() => {
        if (mounted) {
          setLoading(false)
        }
      })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession)
      setLoading(false)

      if (event === 'PASSWORD_RECOVERY') {
        setIsPasswordRecovery(true)
      }

      if (event === 'SIGNED_OUT') {
        setIsPasswordRecovery(false)
      }
    })

    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [])

  const value = useMemo(
    () => ({
      session,
      user: session?.user ?? null,
      loading,
      isPasswordRecovery,
      signInWithPassword: authService.signInWithPassword,
      signUp: authService.signUp,
      signInWithGoogle: async (nextPath?: string) => {
        await authService.signInWithGoogle(nextPath)
      },
      requestPasswordReset: async (email: string) => {
        await authService.requestPasswordReset(email)
      },
      updatePassword: authService.updatePassword,
      signOut: authService.signOut,
    }),
    [isPasswordRecovery, loading, session],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
