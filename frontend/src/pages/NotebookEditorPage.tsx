import { X } from 'lucide-react'
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
import { useAuth } from '../hooks/useAuth'
import type { StudioDocument } from '../types'

export function NotebookEditorPage() {
  const { notebookId = '' } = useParams()
  const navigate = useNavigate()
  const { signOut } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const modalOpen = searchParams.get('modal') === 'add-sources'
  const avatarRef = useRef<HTMLButtonElement | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  const [deselectedByNotebook, setDeselectedByNotebook] = useState<Record<string, string[]>>({})
  const [activeNote, setActiveNote] = useState<StudioDocument | null>(null)
  const [savingNoteId, setSavingNoteId] = useState<string | null>(null)
  const [noteError, setNoteError] = useState<string | null>(null)
  const { loading, notebook, processUploads, profile, addStudioDocument, error: documentError } = useDocuments(notebookId)
  const { messages, isPending, error: chatError, sendMessage, newChat, saveNote } = useChatManager(notebookId)

  const completedSourceNames =
    notebook?.sources.filter((source) => source.status === 'completed').map((source) => source.name) ?? []
  const deselectedSourceNames = notebook ? deselectedByNotebook[notebook.id] ?? [] : []
  const selectedSourceNames = completedSourceNames.filter((name) => !deselectedSourceNames.includes(name))

  const sourcesWithSelection =
    notebook?.sources.map((source) => ({
      ...source,
      selected: selectedSourceNames.includes(source.name),
    })) ?? []

  const allCompletedSelected =
    completedSourceNames.length > 0 && completedSourceNames.every((name) => selectedSourceNames.includes(name))
  const editorError = noteError || chatError || documentError

  const handleSignOut = async () => {
    await signOut()
    navigate('/login', { replace: true })
  }

  const openModal = () => {
    setSearchParams({ modal: 'add-sources' })
  }

  const closeModal = () => {
    setSearchParams({})
  }

  const handleProcessUploads = async (files: File[]) => {
    await processUploads(files)
    closeModal()
  }

  const handleToggleSource = (name: string) => {
    if (!notebook) {
      return
    }

    setDeselectedByNotebook((current) => {
      const deselected = current[notebook.id] ?? []
      const next = deselected.includes(name)
        ? deselected.filter((item) => item !== name)
        : [...deselected, name]

      return {
        ...current,
        [notebook.id]: next,
      }
    })
  }

  const handleToggleAllSources = () => {
    if (!notebook) {
      return
    }

    setDeselectedByNotebook((current) => ({
      ...current,
      [notebook.id]: allCompletedSelected ? completedSourceNames : [],
    }))
  }

  const handleSendMessage = (input: string) => {
    void sendMessage(input, selectedSourceNames)
  }

  const handleNewChat = () => {
    void newChat()
  }

  const handleSaveNote = async (assistantMessageId: string) => {
    setSavingNoteId(assistantMessageId)
    setNoteError(null)

    try {
      const note = await saveNote({ assistantMessageId, documentNames: selectedSourceNames })
      if (note) {
        addStudioDocument(note)
      }
    } catch (err) {
      setNoteError((err as Error).message)
    } finally {
      setSavingNoteId(null)
    }
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
              type="button"
              onClick={handleNewChat}
              disabled={isPending}
              className="rounded-lg border border-outline/60 px-3 py-2 text-[0.72rem] font-semibold text-ink transition hover:bg-white disabled:opacity-60"
            >
              Tạo đoạn chat mới
            </button>
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
            <SourceRail
              sources={sourcesWithSelection}
              onAddSource={openModal}
              onToggleSource={handleToggleSource}
              onToggleAllSources={handleToggleAllSources}
            />
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
                {editorError && (
                  <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[0.72rem] text-red-700">
                    {editorError}
                  </div>
                )}
                <ChatMessageList messages={messages} onSaveNote={handleSaveNote} savingNoteId={savingNoteId} />
              </div>
            </div>
            <ChatComposer
              disabled={isPending || !selectedSourceNames.length}
              helperText={
                selectedSourceNames.length
                  ? `${selectedSourceNames.length} selected source${selectedSourceNames.length > 1 ? 's' : ''}`
                  : 'Select at least one completed source'
              }
              onSubmit={handleSendMessage}
            />
          </section>

          <div className="bg-surface-low px-5 py-4 xl:px-6">
            <StudioDocumentsPanel documents={notebook.studioDocuments} onOpenDocument={setActiveNote} />
          </div>
        </div>
      )}

      {modalOpen && (
        <AddSourcesModal
          open={modalOpen}
          onClose={closeModal}
          onProcess={handleProcessUploads}
        />
      )}

      {activeNote && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(12,15,16,0.25)] px-4 py-8 backdrop-blur-[3px]">
          <article className="max-h-[86vh] w-full max-w-[760px] overflow-y-auto rounded-[14px] bg-white shadow-[0_24px_80px_rgba(43,52,55,0.2)]">
            <div className="sticky top-0 flex items-start justify-between gap-4 border-b border-black/8 bg-white px-6 py-4">
              <div>
                <div className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted">
                  Saved Note
                </div>
                <h2 className="mt-1 text-[1.2rem] font-medium leading-7 text-ink">{activeNote.title}</h2>
              </div>
              <button
                type="button"
                onClick={() => setActiveNote(null)}
                className="rounded-md p-1 text-muted transition hover:bg-surface-low hover:text-ink"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-5 px-6 py-5">
              {activeNote.question && (
                <section>
                  <h3 className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Question</h3>
                  <p className="text-[0.92rem] leading-7 text-ink">{activeNote.question}</p>
                </section>
              )}
              {activeNote.answer && (
                <section>
                  <h3 className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Answer</h3>
                  <p className="whitespace-pre-wrap text-[0.92rem] leading-7 text-ink">{activeNote.answer}</p>
                </section>
              )}
              {Boolean(activeNote.sources?.length) && (
                <section>
                  <h3 className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Sources</h3>
                  <div className="flex flex-wrap gap-2">
                    {activeNote.sources?.map((source, index) => (
                      <span
                        key={`${activeNote.id}-${source.document}-${index}`}
                        className="rounded-md bg-surface-low px-2 py-1 text-[0.68rem] text-muted"
                      >
                        {source.document}
                        {source.page_range ? ` - ${source.page_range}` : ''}
                      </span>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </article>
        </div>
      )}

      <ProfileMenu
        anchorRef={avatarRef}
        open={profileOpen}
        profile={profile}
        onClose={() => setProfileOpen(false)}
        onSignOut={() => {
          void handleSignOut()
        }}
      />
    </main>
  )
}
