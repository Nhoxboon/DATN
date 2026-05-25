export type AuthFormMode = 'login' | 'signup' | 'forgot-password'

export type SourceKind = 'pdf' | 'docx' | 'txt'
export type DocumentStatusValue = 'pending' | 'processing' | 'completed' | 'failed'
export type AudioOverviewStatusValue = 'pending' | 'processing' | 'completed' | 'failed'
export type SlideDeckStatusValue = 'pending' | 'processing' | 'completed' | 'failed'
export type SlideLayoutType =
  | 'TITLE'
  | 'KEY_BULLETS'
  | 'TWO_COLUMNS'
  | 'THREE_FEATURES'
  | 'BIG_STAT'
  | 'FIGURE_FOCUS'
  | 'SECTION_DIVIDER'
  | 'HIGHLIGHT_CARD'
  | 'TIMELINE'
  | 'SUMMARY'

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
  itemType: 'note' | 'audio_overview' | 'slide_deck'
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
  audioUrlExpiresAt?: number | null
}

export interface SlideVisual {
  kind?: 'none' | 'source_page' | 'generated_image'
  prompt?: string | null
  source_index?: number | null
  page?: number | null
  alt?: string | null
  data_url?: string | null
}

export interface SlideDeckSlide {
  slide_number: number
  layout_type: SlideLayoutType
  title: string
  subtitle?: string | null
  bullets?: string[]
  content?: Record<string, unknown>
  visual?: SlideVisual
}

export interface SlideDeckJson {
  title: string
  language?: string | null
  slide_count: number
  slides: SlideDeckSlide[]
  source_count?: number
  image_generation_count?: number
}

export interface SlideDeckDocument extends BaseStudioDocument {
  itemType: 'slide_deck'
  icon: 'presentation'
  status: SlideDeckStatusValue
  deckJson?: SlideDeckJson | null
  documentNames: string[]
  sourceCount: number
  storagePath?: string | null
  contentType?: string | null
  errorMessage?: string | null
  pdfUrl?: string | null
  pdfUrlExpiresAt?: number | null
}

export type StudioDocument = StudioNoteDocument | AudioOverviewDocument | SlideDeckDocument

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

export interface BackendSlideDeck {
  id: string
  notebook_id: string
  status: SlideDeckStatusValue
  storage_path: string | null
  title: string
  deck_json: SlideDeckJson | null
  document_names: string[]
  source_count: number
  content_type: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface BackendSlideDeckUrl {
  pdf_url: string
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
