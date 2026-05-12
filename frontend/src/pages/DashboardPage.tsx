import { FilePlus2, PlusCircle, Search } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { NotebookCard } from '../components/history/NotebookCard'
import { ProfileMenu } from '../components/layout/ProfileMenu'
import { Button } from '../components/shared/Button'
import { useDocuments } from '../hooks/useDocuments'
import { useAuth } from '../hooks/useAuth'

export function DashboardPage() {
  const navigate = useNavigate()
  const { signOut } = useAuth()
  const { loading, summaries, profile, createNotebook, deleteNotebook, renameNotebook, error } = useDocuments()
  const avatarRef = useRef<HTMLButtonElement | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  const [creatingNotebook, setCreatingNotebook] = useState(false)

  const handleSignOut = async () => {
    await signOut()
    navigate('/login', { replace: true })
  }

  const handleCreateNotebook = async () => {
    if (creatingNotebook) {
      return
    }

    setCreatingNotebook(true)
    try {
      const created = await createNotebook()
      navigate(`/notebooks/${created.id}`)
    } catch {
      setCreatingNotebook(false)
    }
  }

  const handleDeleteNotebook = async (id: string) => {
    const notebook = summaries.find((item) => item.id === id)
    if (!window.confirm(`Delete "${notebook?.title ?? 'this notebook'}"?`)) {
      return
    }

    await deleteNotebook(id)
  }

  const handleRenameNotebook = async (id: string) => {
    const notebook = summaries.find((item) => item.id === id)
    const nextTitle = window.prompt('Rename notebook', notebook?.title ?? '')

    if (!nextTitle?.trim()) {
      return
    }

    await renameNotebook(id, nextTitle.trim())
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="w-full px-4 py-6 sm:px-6 lg:px-10 lg:py-7 xl:px-12 2xl:px-16">
        <div className="mb-10 flex items-center justify-between gap-4">
          <div className="text-sm font-medium text-primary">The Scholarly Curator</div>
          <div className="flex items-center gap-3">
            <label className="relative hidden sm:block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <input
                type="search"
                placeholder="Search research..."
                className="h-9 w-56 rounded-full border-none bg-white/75 pl-9 pr-4 text-xs text-ink shadow-[inset_0_0_0_1px_rgba(171,179,183,0.18)] outline-none placeholder:text-muted"
              />
            </label>
            <button
              ref={avatarRef}
              type="button"
              onClick={() => setProfileOpen((current) => !current)}
              className="flex h-7 w-7 items-center justify-center rounded-full bg-[#eec78c] text-[0.6rem] font-semibold text-white"
              aria-label="Open profile menu"
            >
              {profile?.avatarLabel ?? 'AT'}
            </button>
          </div>
        </div>

        <div className="mb-7 flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <h1 className="font-sans text-[2.15rem] font-semibold tracking-[-0.03em] text-ink">
              Research Studio
            </h1>
            <p className="max-w-135 text-sm leading-6 text-muted">
              Organize your intellectual output with editorial precision. Select a notebook to continue your discovery.
            </p>
          </div>

          <Button
            className="h-10 rounded-lg px-4 py-0 text-xs font-semibold shadow-none"
            disabled={creatingNotebook}
            onClick={() => {
              void handleCreateNotebook()
            }}
          >
            <PlusCircle className="h-3.5 w-3.5" />
            {creatingNotebook ? 'Creating...' : 'Create New Notebook'}
          </Button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {loading
          ? Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="h-38 animate-pulse rounded-[10px] bg-white/70" />
            ))
          : summaries.map((notebook) => (
              <NotebookCard
                key={notebook.id}
                notebook={notebook}
                onOpen={(id) => navigate(`/notebooks/${id}`)}
                onRename={(id) => {
                  void handleRenameNotebook(id)
                }}
                onDelete={(id) => {
                  void handleDeleteNotebook(id)
                }}
              />
            ))}

        <button
          type="button"
          disabled={creatingNotebook}
          onClick={() => {
            void handleCreateNotebook()
          }}
          className="flex min-h-38 flex-col items-center justify-center rounded-[10px] border border-dashed border-outline/80 bg-transparent px-8 py-6 text-center transition hover:bg-white/45 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-[10px] bg-surface-high text-primary">
            <FilePlus2 className="h-4 w-4" />
          </div>
          <div className="space-y-1.5">
            <h3 className="text-sm font-medium text-ink">{creatingNotebook ? 'Creating...' : 'New Research Project'}</h3>
            <p className="mx-auto max-w-52.5 text-[0.72rem] leading-5 text-muted">
              Create a blank workspace to start collecting sources.
            </p>
          </div>
        </button>
        </section>

        <ProfileMenu
          anchorRef={avatarRef}
          open={profileOpen}
          profile={profile}
          onClose={() => setProfileOpen(false)}
          onSignOut={() => {
            void handleSignOut()
          }}
        />
      </div>
    </main>
  )
}
