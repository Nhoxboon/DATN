import { api } from './api';

interface DocumentListResponse {
  documents: string[];
}

export interface DocumentUploadResponse {
  status: string;
  document_name: string;
  chunks_processed: number;
  storage_path: string;
  public_url?: string | null;
}

export const documentService = {
  async list(): Promise<string[]> {
    const data = await api.get<DocumentListResponse>('/documents/');
    return data.documents || [];
  },

  async upload(file: File): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/documents/upload/file', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      let detail = response.statusText;

      try {
        const errorData = await response.json();
        detail = errorData.detail || detail;
      } catch {
        // Ignore JSON parsing errors and fall back to status text.
      }

      throw new Error(`Upload failed: ${detail}`);
    }

    return response.json();
  },

  async delete(documentName: string): Promise<void> {
    return api.delete<void>(`/documents/${documentName}`);
  },
};
