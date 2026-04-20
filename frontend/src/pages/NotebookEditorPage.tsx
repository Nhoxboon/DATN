import { useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ProfileMenu } from '../components/layout/ProfileMenu'
import { SourceRail } from '../components/sources/SourceRail'
import { AddSourcesModal } from '../components/sources/AddSourcesModal'
import { SynthesisCard } from '../components/chat/SynthesisCard'
import { ChatComposer } from '../components/chat/ChatComposer'
import { ChatMessageList } from '../components/chat/ChatMessageList'
import { StudioDocumentsPanel } from '../components/history/StudioDocumentsPanel'
import { useChatManager } from '../hooks/useChatManager'
import { useDocuments } from '../hooks/useDocuments'

export function NotebookEditorPage() {
  const { notebookId = '' } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const modalOpen = searchParams.get('modal') === 'add-sources'
  const avatarRef = useRef<HTMLButtonElement | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  const { loading, notebook, uploadPool, processUploads, profile } = useDocuments(notebookId)
  const { messages, isPending, sendMessage } = useChatManager(notebookId)

  const openModal = () => {
    setSearchParams({ modal: 'add-sources' })
  }

  const closeModal = () => {
    setSearchParams({})
  }

  const handleProcessUploads = async (uploadIds: string[]) => {
    await processUploads(uploadIds)
    closeModal()
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="border-b border-black/10 bg-background px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-4">
            <button
              type="button"
              onClick={() => navigate('/dashboard')}
              className="shrink-0 text-sm font-medium text-primary hover:text-primary-deep"
            >
              The Scholarly Curator
            </button>
            <div className="truncate text-[0.68rem] text-muted">
              {notebook?.title ?? 'Notebook Editor & Chat'}
            </div>
          </div>
          <div className="flex items-center gap-3">
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
      </div>

      {loading || !notebook ? (
        <div className="grid min-h-[calc(100vh-49px)] gap-0 lg:grid-cols-[21.875%_53.125%_25%]">
          <div className="animate-pulse bg-surface-low" />
          <div className="animate-pulse border-x border-black/10 bg-white" />
          <div className="animate-pulse bg-surface-low" />
        </div>
      ) : (
        <div className="grid min-h-[calc(100vh-49px)] gap-0 lg:grid-cols-[21.875%_53.125%_25%]">
          <div className="bg-surface-low px-5 py-4 xl:px-6">
            <SourceRail sources={notebook.sources} onAddSource={openModal} />
          </div>

          <section className="flex min-h-0 flex-col border-x border-black/10 bg-white">
            <div className="flex-1 overflow-y-auto">
              <SynthesisCard notebook={notebook} />
              <div className="px-6 pb-4 sm:px-7">
                {isPending && (
                  <div className="mb-3 text-[0.58rem] uppercase tracking-[0.14em] text-muted">
                    Responding...
                  </div>
                )}
                <ChatMessageList messages={messages} />
              </div>
            </div>
            <ChatComposer disabled={isPending} onSubmit={sendMessage} />
          </section>

          <div className="bg-surface-low px-5 py-4 xl:px-6">
            <StudioDocumentsPanel documents={notebook.studioDocuments} />
          </div>
        </div>
      )}

      {modalOpen && (
        <AddSourcesModal
          open={modalOpen}
          uploads={uploadPool}
          onClose={closeModal}
          onProcess={handleProcessUploads}
        />
      )}

      <ProfileMenu
        anchorRef={avatarRef}
        open={profileOpen}
        profile={profile}
        onClose={() => setProfileOpen(false)}
      />
    </main>
  )
}
