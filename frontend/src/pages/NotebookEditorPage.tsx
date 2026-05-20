import { Check, Pencil, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ProfileMenu } from '../components/layout/ProfileMenu'
import { SourceRail } from '../components/sources/SourceRail'
import { AddSourcesModal } from '../components/sources/AddSourcesModal'
import { SynthesisCard } from '../components/chat/SynthesisCard'
import { ChatComposer } from '../components/chat/ChatComposer'
import { ChatMessageList, RichAnswerContent } from '../components/chat/ChatMessageList'
import { AudioOverviewPlayer, type AudioPlaybackState } from '../components/history/AudioOverviewPlayer'
import { StudioDocumentsPanel } from '../components/history/StudioDocumentsPanel'
import { useChatManager } from '../hooks/useChatManager'
import { useDocuments } from '../hooks/useDocuments'
import { useAuth } from '../hooks/useAuth'
import type { AudioOverviewDocument, SourceItem, StudioNoteDocument } from '../types'

export function NotebookEditorPage() {
  const { notebookId = '' } = useParams()
  const navigate = useNavigate()
  const { signOut } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const modalOpen = searchParams.get('modal') === 'add-sources'
  const avatarRef = useRef<HTMLButtonElement | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  const [deselectedByNotebook, setDeselectedByNotebook] = useState<Record<string, string[]>>({})
  const [activeItemId, setActiveItemId] = useState<string | null>(null)
  const [savingNoteId, setSavingNoteId] = useState<string | null>(null)
  const [creatingAudio, setCreatingAudio] = useState(false)
  const [noteError, setNoteError] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [audioPlaybackById, setAudioPlaybackById] = useState<Record<string, AudioPlaybackState>>({})
  const [activeAudioPlayerId, setActiveAudioPlayerId] = useState<string | null>(null)
  const {
    loading,
    notebook,
    processUploads,
    profile,
    addStudioDocument,
    renameNotebook,
    renameSource,
    deleteSource,
    renameNote,
    deleteNote,
    createAudioOverview,
    deleteAudioOverview,
    refreshAudioOverviewUrl,
    error: documentError,
  } = useDocuments(notebookId)
  const { messages, isPending, error: chatError, sendMessage, newChat, saveNote } = useChatManager(notebookId)

  const completedSourceNames =
    notebook?.sources.filter((source) => source.status === 'completed').map((source) => source.name) ?? []
  const deselectedSourceNames = notebook ? deselectedByNotebook[notebook.id] ?? [] : []
  const selectedSourceNames = completedSourceNames.filter((name) => !deselectedSourceNames.includes(name))
  const activeItem = activeItemId
    ? notebook?.studioDocuments.find((document) => document.id === activeItemId) ?? null
    : null

  const sourcesWithSelection =
    notebook?.sources.map((source) => ({
      ...source,
      selected: selectedSourceNames.includes(source.name),
    })) ?? []

  const allCompletedSelected =
    completedSourceNames.length > 0 && completedSourceNames.every((name) => selectedSourceNames.includes(name))
  const editorError = noteError || chatError || documentError

  const handleAudioPlaybackChange = (documentId: string, playbackState: AudioPlaybackState) => {
    setAudioPlaybackById((current) => ({
      ...current,
      [documentId]: playbackState,
    }))
  }

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

  const startEditingTitle = () => {
    if (!notebook) {
      return
    }

    setTitleDraft(notebook.title)
    setEditingTitle(true)
  }

  const cancelEditingTitle = () => {
    setTitleDraft('')
    setEditingTitle(false)
  }

  const submitTitle = async () => {
    if (!notebook || renaming) {
      return
    }

    const nextTitle = titleDraft.trim()
    if (!nextTitle || nextTitle === notebook.title) {
      cancelEditingTitle()
      return
    }

    setRenaming(true)
    try {
      await renameNotebook(notebook.id, nextTitle)
      cancelEditingTitle()
    } catch (err) {
      setNoteError((err as Error).message)
    } finally {
      setRenaming(false)
    }
  }

  const handleProcessUploads = (files: File[]) => {
    closeModal()
    void processUploads(files)
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

  const handleRenameSource = async (source: SourceItem) => {
    if (!notebook) {
      return
    }

    const nextName = window.prompt('Rename source', source.name)
    const cleanName = nextName?.trim()

    if (!cleanName || cleanName === source.name) {
      return
    }

    setNoteError(null)
    try {
      await renameSource(source.name, cleanName)
      setDeselectedByNotebook((current) => {
        const deselected = current[notebook.id] ?? []
        if (!deselected.includes(source.name)) {
          return current
        }

        return {
          ...current,
          [notebook.id]: deselected.map((name) => (name === source.name ? cleanName.replace(/\.pdf$/i, '') : name)),
        }
      })
    } catch (err) {
      setNoteError((err as Error).message)
    }
  }

  const handleDeleteSource = async (source: SourceItem) => {
    if (!notebook) {
      return
    }

    if (!window.confirm(`Delete source "${source.name}"?`)) {
      return
    }

    setNoteError(null)
    try {
      await deleteSource(source.name)
      setDeselectedByNotebook((current) => ({
        ...current,
        [notebook.id]: (current[notebook.id] ?? []).filter((name) => name !== source.name),
      }))
    } catch (err) {
      setNoteError((err as Error).message)
    }
  }

  const handleRenameNote = async (document: StudioNoteDocument) => {
    const nextTitle = window.prompt('Rename note', document.title)
    const cleanTitle = nextTitle?.trim()

    if (!cleanTitle || cleanTitle === document.title) {
      return
    }

    setNoteError(null)
    try {
      await renameNote(document.id, cleanTitle)
    } catch (err) {
      setNoteError((err as Error).message)
    }
  }

  const handleDeleteNote = async (document: StudioNoteDocument) => {
    if (!window.confirm(`Delete note "${document.title}"?`)) {
      return
    }

    setNoteError(null)
    try {
      await deleteNote(document.id)
      setActiveItemId((current) => (current === document.id ? null : current))
    } catch (err) {
      setNoteError((err as Error).message)
    }
  }

  const handleCreateAudioOverview = async () => {
    if (!selectedSourceNames.length || creatingAudio) {
      return
    }

    setCreatingAudio(true)
    setNoteError(null)
    try {
      await createAudioOverview(selectedSourceNames)
    } catch (err) {
      setNoteError((err as Error).message)
    } finally {
      setCreatingAudio(false)
    }
  }

  const handleDeleteAudioOverview = async (document: AudioOverviewDocument) => {
    if (!window.confirm(`Delete audio overview "${document.title}"?`)) {
      return
    }

    setNoteError(null)
    try {
      await deleteAudioOverview(document.id)
      setActiveItemId((current) => (current === document.id ? null : current))
    } catch (err) {
      setNoteError((err as Error).message)
    }
  }

  const handleRetryAudioOverview = async (document: AudioOverviewDocument) => {
    const documentNames = document.documentNames.length ? document.documentNames : selectedSourceNames
    if (!documentNames.length || creatingAudio) {
      return
    }

    setCreatingAudio(true)
    setNoteError(null)
    try {
      await createAudioOverview(documentNames)
    } catch (err) {
      setNoteError((err as Error).message)
    } finally {
      setCreatingAudio(false)
    }
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
            {editingTitle ? (
              <div className="flex min-w-0 items-center gap-2">
                <input
                  autoFocus
                  value={titleDraft}
                  disabled={renaming}
                  onChange={(event) => setTitleDraft(event.target.value)}
                  onBlur={() => {
                    void submitTitle()
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      void submitTitle()
                    }
                    if (event.key === 'Escape') {
                      event.preventDefault()
                      cancelEditingTitle()
                    }
                  }}
                  className="h-7 min-w-0 max-w-[260px] rounded-md border border-outline/60 bg-white px-2 text-[0.76rem] text-ink outline-none focus:border-primary"
                />
                <Check className="h-3.5 w-3.5 text-primary" />
              </div>
            ) : (
              <button
                type="button"
                onDoubleClick={startEditingTitle}
                title="Double click to rename"
                className="group flex min-w-0 items-center gap-1.5 text-left text-[0.68rem] text-muted"
              >
                <span className="truncate">{notebook?.title ?? 'Notebook Editor & Chat'}</span>
                <Pencil className="h-3 w-3 opacity-0 transition group-hover:opacity-70" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleNewChat}
              disabled={isPending}
              className="rounded-lg border border-outline/60 px-3 py-2 text-[0.72rem] font-semibold text-ink transition hover:bg-white disabled:opacity-60"
            >
              New chat
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

      {loading && !notebook ? (
        <div className="grid h-[calc(100vh-49px)] min-h-0 gap-0 lg:grid-cols-[21.875%_53.125%_25%]">
          <div className="animate-pulse bg-surface-low" />
          <div className="animate-pulse border-x border-black/10 bg-white" />
          <div className="animate-pulse bg-surface-low" />
        </div>
      ) : notebook ? (
        <div className="grid h-[calc(100vh-49px)] min-h-0 gap-0 lg:grid-cols-[21.875%_53.125%_25%]">
          <div className="bg-surface-low px-5 py-4 xl:px-6">
            <SourceRail
              sources={sourcesWithSelection}
              onAddSource={openModal}
              onToggleSource={handleToggleSource}
              onToggleAllSources={handleToggleAllSources}
              onRenameSource={(source) => {
                void handleRenameSource(source)
              }}
              onDeleteSource={(source) => {
                void handleDeleteSource(source)
              }}
            />
          </div>

          <section className="flex h-full min-h-0 flex-col border-x border-black/10 bg-white">
            <div className="min-h-0 flex-1 overflow-hidden px-6 pb-4 sm:px-7">
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
                <ChatMessageList
                  messages={messages}
                  intro={<SynthesisCard notebook={notebook} />}
                  onSaveNote={handleSaveNote}
                  savingNoteId={savingNoteId}
                />
            </div>
            <ChatComposer
              disabled={isPending || !selectedSourceNames.length}
              helperText={
                selectedSourceNames.length
                  ? `${selectedSourceNames.length} selected source${selectedSourceNames.length > 1 ? 's' : ''}`
                  : 'Select at least one completed source'
              }
              disclaimerText="The Scholarly Curator may provide inaccurate information; please carefully verify the answers you receive."
              onSubmit={handleSendMessage}
            />
          </section>

          <div className="bg-surface-low px-5 py-4 xl:px-6">
            <StudioDocumentsPanel
              documents={notebook.studioDocuments}
              onOpenDocument={(document) => setActiveItemId(document.id)}
              onCreateAudioOverview={() => {
                void handleCreateAudioOverview()
              }}
              onRenameNote={(document) => {
                void handleRenameNote(document)
              }}
              onDeleteNote={(document) => {
                void handleDeleteNote(document)
              }}
              onDeleteAudioOverview={(document) => {
                void handleDeleteAudioOverview(document)
              }}
              onRetryAudioOverview={(document) => {
                void handleRetryAudioOverview(document)
              }}
              onRefreshAudioUrl={(document) => refreshAudioOverviewUrl(document.id)}
              audioPlaybackById={audioPlaybackById}
              activeAudioPlayerId={activeAudioPlayerId}
              onAudioPlaybackChange={handleAudioPlaybackChange}
              onActiveAudioPlayerChange={setActiveAudioPlayerId}
              audioDisabled={!selectedSourceNames.length}
              audioBusy={creatingAudio}
            />
          </div>
        </div>
      ) : (
        <div className="flex h-[calc(100vh-49px)] items-center justify-center bg-white px-6 text-sm text-muted">
          {documentError || 'Could not load this notebook.'}
        </div>
      )}

      {modalOpen && (
        <AddSourcesModal
          open={modalOpen}
          onClose={closeModal}
          onProcess={handleProcessUploads}
        />
      )}

      {activeItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(12,15,16,0.25)] px-4 py-8 backdrop-blur-[3px]">
          <article className="max-h-[86vh] w-full max-w-[760px] overflow-y-auto rounded-[14px] bg-white shadow-[0_24px_80px_rgba(43,52,55,0.2)]">
            <div className="sticky top-0 flex items-start justify-between gap-4 border-b border-black/8 bg-white px-6 py-4">
              <div>
                <div className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted">
                  {activeItem.itemType === 'audio_overview' ? 'Audio Overview' : 'Saved Note'}
                </div>
                <h2 className="mt-1 text-[1.2rem] font-medium leading-7 text-ink">{activeItem.title}</h2>
              </div>
              <button
                type="button"
                onClick={() => setActiveItemId(null)}
                className="rounded-md p-1 text-muted transition hover:bg-surface-low hover:text-ink"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-5 px-6 py-5">
              {activeItem.itemType === 'audio_overview' ? (
                <>
                  {activeItem.status === 'completed' && (
                    <section>
                      <h3 className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Audio</h3>
                      <AudioOverviewPlayer
                        document={activeItem}
                        onRefreshAudioUrl={(document) => refreshAudioOverviewUrl(document.id)}
                        playbackState={audioPlaybackById[activeItem.id]}
                        activePlayerId={activeAudioPlayerId}
                        playerId={`modal-${activeItem.id}`}
                        onPlaybackStateChange={handleAudioPlaybackChange}
                        onActivePlayerChange={setActiveAudioPlayerId}
                        className="w-full"
                      />
                    </section>
                  )}
                  {activeItem.scriptText && (
                    <section>
                      <h3 className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Script</h3>
                      <div className="whitespace-pre-wrap text-[0.92rem] leading-7 text-ink">{activeItem.scriptText}</div>
                    </section>
                  )}
                  {Boolean(activeItem.documentNames.length) && (
                    <section>
                      <h3 className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Sources</h3>
                      <div className="flex flex-wrap gap-2">
                        {activeItem.documentNames.map((documentName) => (
                          <span
                            key={`${activeItem.id}-${documentName}`}
                            className="rounded-md bg-surface-low px-2 py-1 text-[0.68rem] text-muted"
                          >
                            {documentName}
                          </span>
                        ))}
                      </div>
                    </section>
                  )}
                </>
              ) : (
                <>
                  {activeItem.question && (
                    <section>
                      <h3 className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Question</h3>
                      <p className="text-[0.92rem] leading-7 text-ink">{activeItem.question}</p>
                    </section>
                  )}
                  {activeItem.answer && (
                    <section>
                      <h3 className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Answer</h3>
                      <div className="text-[0.92rem] leading-7 text-ink">
                        <RichAnswerContent content={activeItem.answer} sources={activeItem.sources} />
                      </div>
                    </section>
                  )}
                  {Boolean(activeItem.sources?.length) && (
                    <section>
                      <h3 className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-muted">Sources</h3>
                      <div className="flex flex-wrap gap-2">
                        {activeItem.sources?.map((source, index) => (
                          <span
                            key={`${activeItem.id}-${source.document}-${index}`}
                            className="rounded-md bg-surface-low px-2 py-1 text-[0.68rem] text-muted"
                          >
                            {source.document}
                            {source.page_range ? ` - ${source.page_range}` : ''}
                          </span>
                        ))}
                      </div>
                    </section>
                  )}
                </>
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
