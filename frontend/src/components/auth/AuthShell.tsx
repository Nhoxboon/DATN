import type { PropsWithChildren, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { LogoMark } from '../shared/LogoMark'

interface AuthShellProps {
  eyebrow?: string
  title: string
  description: string
  asideTitle?: string
  asideDescription?: string
  footerPrompt?: ReactNode
}

export function AuthShell({
  children,
  eyebrow,
  title,
  description,
  asideTitle = 'Curate your intellectual legacy.',
  asideDescription = 'Join a focused workspace where research meets craftsmanship. Every note is a stroke of genius, organized in a system designed for clarity.',
  footerPrompt,
}: PropsWithChildren<AuthShellProps>) {
  return (
    <main className="min-h-screen bg-background px-5 py-6 text-ink sm:px-8 lg:px-10">
      <div className="mx-auto grid min-h-[calc(100vh-3rem)] max-w-7xl overflow-hidden rounded-[32px] bg-surface-low shadow-float lg:grid-cols-[1.05fr_0.95fr]">
        <section className="relative hidden overflow-hidden bg-[radial-gradient(circle_at_top_left,rgba(0,91,192,0.18),transparent_42%),radial-gradient(circle_at_bottom_right,rgba(112,68,193,0.12),transparent_36%),linear-gradient(160deg,rgba(255,255,255,0.78),rgba(241,244,246,0.98))] p-10 lg:flex lg:flex-col lg:justify-between xl:p-14">
          <LogoMark />
          <div className="max-w-xl space-y-6">
            <p className="font-display text-xs uppercase tracking-[0.38em] text-muted">The Digital Atelier</p>
            <h1 className="font-display text-5xl font-semibold leading-[1.02] text-ink">{asideTitle}</h1>
            <p className="max-w-lg text-base leading-8 text-muted">{asideDescription}</p>
            <div className="glass-panel max-w-md space-y-3 rounded-[28px] p-6">
              <p className="text-xs uppercase tracking-[0.28em] text-muted">Editorial Workspace</p>
              <p className="font-display text-2xl text-ink">A research studio shaped for focus, synthesis, and presentation.</p>
            </div>
          </div>
          <div className="flex items-center justify-between text-sm text-muted">
            <span>© 2024 Scholar Script. Designed for the Digital Atelier.</span>
            <div className="flex gap-5">
              <Link to="/login" className="hover:text-ink">
                Privacy
              </Link>
              <Link to="/login" className="hover:text-ink">
                Terms
              </Link>
              <Link to="/login" className="hover:text-ink">
                Support
              </Link>
            </div>
          </div>
        </section>

        <section className="flex flex-col justify-between bg-surface p-6 sm:p-8 lg:p-12 xl:p-14">
          <div className="mb-12 flex items-center justify-between lg:hidden">
            <LogoMark compact />
          </div>

          <div className="mx-auto flex w-full max-w-lg flex-1 flex-col justify-center">
            <div className="space-y-5">
              {eyebrow && <p className="font-display text-xs uppercase tracking-[0.35em] text-muted">{eyebrow}</p>}
              <div className="space-y-3">
                <h2 className="font-display text-4xl font-semibold leading-tight text-ink">{title}</h2>
                <p className="max-w-md text-base leading-7 text-muted">{description}</p>
              </div>
            </div>
            <div className="mt-8">{children}</div>
            {footerPrompt && <div className="mt-8 text-sm text-muted">{footerPrompt}</div>}
          </div>

          <div className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-white/60 pt-6 text-sm text-muted lg:hidden">
            <span>© 2024 Scholar Script. Designed for the Digital Atelier.</span>
            <div className="flex gap-4">
              <Link to="/login" className="hover:text-ink">
                Privacy
              </Link>
              <Link to="/login" className="hover:text-ink">
                Terms
              </Link>
              <Link to="/login" className="hover:text-ink">
                Support
              </Link>
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}
