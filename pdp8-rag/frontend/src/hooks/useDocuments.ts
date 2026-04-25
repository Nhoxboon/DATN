import { useState, useEffect } from 'react';
import { documentService } from '../services/documentService';
import type { UseDocumentsReturn } from '../types';

export function useDocuments(): UseDocumentsReturn {
  const [documents, setDocuments] = useState<string[]>([]);
  const [currentDocument, setCurrentDocument] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    try {
      setLoading(true);
      setError(null);
      const docs = await documentService.list();
      setDocuments(docs);
      if (docs.length > 0 && !currentDocument) {
        setCurrentDocument(docs[0]);
      }
    } catch (err) {
      setError((err as Error).message);
      console.error('Failed to load documents:', err);
    } finally {
      setLoading(false);
    }
  };

  const selectDocument = (docName: string) => {
    setCurrentDocument(docName);
  };

  const uploadDocument = async (file: File) => {
    try {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        throw new Error('Only PDF files are supported');
      }

      setUploading(true);
      setError(null);
      const result = await documentService.upload(file);
      await loadDocuments();
      setCurrentDocument(result.document_name);
    } catch (err) {
      const message = (err as Error).message;
      setError(message);
      console.error('Failed to upload document:', err);
      throw err;
    } finally {
      setUploading(false);
    }
  };

  return {
    documents,
    currentDocument,
    selectDocument,
    uploadDocument,
    loading,
    uploading,
    error,
    reload: loadDocuments,
  };
}
