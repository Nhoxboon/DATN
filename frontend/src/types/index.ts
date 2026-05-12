export type AuthFormMode = 'login' | 'signup' | 'forgot-password'

export type SourceKind = 'pdf' | 'docx' | 'txt'
export type DocumentStatusValue = 'pending' | 'processing' | 'completed' | 'failed'

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

export interface StudioDocument {
  id: string
  title: string
  excerpt: string
  updatedAt: string
  icon: 'description' | 'table_chart'
  question?: string
  answer?: string
  sources?: RagSource[]
  documentNames?: string[]
}

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

export interface BackendNotebookDetail extends BackendNotebookSummary {
  documents: BackendDocumentStatus[]
  notes: BackendNotebookNote[]
}

export interface RagSource {
  content: string
  document: string
  pages?: number[]
  page_range: string
  similarity: number
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
