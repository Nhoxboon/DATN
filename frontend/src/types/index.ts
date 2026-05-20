export type AuthFormMode = 'login' | 'signup' | 'forgot-password'

export type SourceKind = 'pdf' | 'docx' | 'txt'
export type DocumentStatusValue = 'pending' | 'processing' | 'completed' | 'failed'
export type AudioOverviewStatusValue = 'pending' | 'processing' | 'completed' | 'failed'

export interface UserProfile {
  id: string
  name: string
  role: string
  avatarLabel: string
}

export interface NotebookSummary {
  id: string
  category: string
  title: string
  sourceCount: number
  updatedAt: string
  description: string
}

export interface SourceItem {
  id: string
  name: string
  kind: SourceKind
  meta: string
  selected: boolean
  status?: DocumentStatusValue
  errorMessage?: string | null
}

interface BaseStudioDocument {
  id: string
  itemType: 'note' | 'audio_overview'
  title: string
  excerpt: string
  updatedAt: string
  sortTimestamp?: string
}

export interface StudioNoteDocument extends BaseStudioDocument {
  itemType: 'note'
  icon: 'description' | 'table_chart'
  question?: string
  answer?: string
  sources?: RagSource[]
  documentNames?: string[]
}

export interface AudioOverviewDocument extends BaseStudioDocument {
  itemType: 'audio_overview'
  icon: 'audio'
  status: AudioOverviewStatusValue
  style?: string | null
  scriptText?: string | null
  documentNames: string[]
  durationSeconds?: number | null
  storagePath?: string | null
  contentType?: string | null
  errorMessage?: string | null
  audioUrl?: string | null
}

export type StudioDocument = StudioNoteDocument | AudioOverviewDocument

export interface ChatMessage {
  id: string
  role: 'assistant' | 'user'
  content: string
  timestamp: string
  sources?: RagSource[]
  saved?: boolean
  pending?: boolean
  error?: boolean
  progressLabel?: string
  answerMode?: 'singlehop' | 'multihop'
  strategy?: string | null
  strategyReasoning?: string | null
}

export interface UploadCandidate {
  id: string
  name: string
  kind: SourceKind
  sizeLabel: string
}

export interface NotebookDetail extends NotebookSummary {
  synthesisTitle: string
  synthesisBody: string
  synthesisBullets: string[]
  sources: SourceItem[]
  studioDocuments: StudioDocument[]
}

export interface BackendNotebookSummary {
  id: string
  title: string
  description: string | null
  source_count: number
  created_at: string
  updated_at: string
}

export interface BackendDocumentStatus {
  id: string | null
  document_name: string
  status: DocumentStatusValue
  total_chunks: number | null
  processed_chunks: number | null
  error_message: string | null
  created_at: string | null
  updated_at: string | null
}

export interface BackendNotebookNote {
  id: string
  question: string
  answer: string
  sources: RagSource[]
  document_names: string[]
  created_at: string
  updated_at: string
}

export interface BackendAudioOverview {
  id: string
  notebook_id: string
  status: AudioOverviewStatusValue
  storage_path: string | null
  title: string
  style: string | null
  script_text: string | null
  document_names: string[]
  duration_seconds: number | null
  content_type: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface BackendAudioOverviewUrl {
  audio_url: string
  expires_in: number
}

export interface BackendNotebookDetail extends BackendNotebookSummary {
  documents: BackendDocumentStatus[]
  notes: BackendNotebookNote[]
}

export interface RagSource {
  content: string
  document: string
  chunk_id?: number | null
  pages?: number[]
  page_range: string
  similarity?: number | null
  metadata?: Record<string, unknown>
  content_type?: string
  has_visual?: boolean
  image_url?: string | null
}

export interface BackendChatMessage {
  id: string
  role: 'assistant' | 'user' | 'system'
  content: string
  sources: RagSource[]
  created_at: string
}

export interface BackendChatCurrent {
  session_id: string
  messages: BackendChatMessage[]
}

export interface BackendChatSendResponse extends BackendChatCurrent {
  answer: string
  sources: RagSource[]
  strategy?: string | null
  strategy_reasoning?: string | null
}
