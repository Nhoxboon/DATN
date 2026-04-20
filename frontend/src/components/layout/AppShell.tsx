import type { PropsWithChildren } from 'react'

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="min-h-screen bg-background px-4 py-4 sm:px-6 lg:px-8">
      <div className="mx-auto min-h-[calc(100vh-2rem)] max-w-[1600px] rounded-[34px] bg-surface-low px-5 py-6 shadow-float sm:px-7 sm:py-8 lg:px-10 lg:py-10">
        {children}
      </div>
    </div>
  )
}
