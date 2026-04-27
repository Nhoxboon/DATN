// Message types
export interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  strategy?: string;
  strategy_reasoning?: string;
  isFromHistory?: boolean;
}

// Source types
export interface Source {
  document: string;
  page_range: string;
  content: string;
  similarity: number;
  metadata?: Record<string, unknown>;
  content_type?: string;
  has_visual?: boolean;
  image_url?: string | null;
}


// History types
export interface HistoryItem {
  id: number;
  timestamp: string;
  preview: string;
  userMessage: string;
  assistantResponse: string;
  sources: Source[];
}
// Chat Session - Each chat is a full conversation
export interface ChatSession {
  id: string; // Unique ID for each chat
  messages: Message[];
  streaming: boolean;
  createdAt: string;
  updatedAt: string;
  preview: string; // First user message preview
}

// API types
export interface StreamData {
  type: 'token' | 'metadata' | 'done' | 'error';
  content?: string;
  message?: string;
  sources?: Source[];
  strategy?: string;
  strategy_reasoning?: string;
}

// Component prop types
export interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export interface ChatMessagesProps {
  messages: Message[];
  streaming: boolean;
  sessionId: string;
}

export interface HeaderProps {
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onNewChat: () => void;
}

export interface HistoryPanelProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

export interface MessageProps {
  message: Message;
  index: number;
  skipTypewriter?: boolean;
}

export interface SourcesPanelProps {
  documents: string[];
  currentDocument: string | null;
  onSelectDocument: (doc: string) => void;
  onUploadDocument: (file: File) => Promise<void>;
  loading: boolean;
  uploading: boolean;
  error: string | null;
}

// Hook return types
export interface UseDocumentsReturn {
  documents: string[];
  currentDocument: string | null;
  selectDocument: (docName: string) => void;
  uploadDocument: (file: File) => Promise<void>;
  loading: boolean;
  uploading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

export interface UseChatReturn {
  sessions: ChatSession[];
  activeSessionId: string;
  currentSession: ChatSession | null;
  error: string | null;
  sendMessage: (message: string, documentName: string | null) => Promise<void>;
  switchToSession: (sessionId: string) => void;
  createNewChat: () => void;
  deleteSession: (sessionId: string) => void;
}

export interface UseThemeReturn {
  theme: 'light' | 'dark';
  toggleTheme: () => void;
}
