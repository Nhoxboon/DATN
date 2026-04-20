export type AuthFormMode = 'login' | 'signup' | 'forgot-password'

export type SourceKind = 'pdf' | 'docx' | 'txt'

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
}

export interface StudioDocument {
  id: string
  title: string
  excerpt: string
  updatedAt: string
  icon: 'description' | 'table_chart'
}

export interface ChatMessage {
  id: string
  role: 'assistant' | 'user'
  content: string
  timestamp: string
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
