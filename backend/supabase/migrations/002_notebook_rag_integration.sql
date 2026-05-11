-- DATN notebook RAG integration.

CREATE EXTENSION IF NOT EXISTS vector;

-- Align document chunks with the copied pdp8-rag runtime.
DROP INDEX IF EXISTS public.documents_embedding_idx;
ALTER TABLE public.documents
    ALTER COLUMN embedding TYPE halfvec(3072) USING embedding::halfvec(3072);
ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS pages INTEGER[],
    ADD COLUMN IF NOT EXISTS page_range TEXT;

CREATE INDEX IF NOT EXISTS documents_embedding_idx
ON public.documents USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS documents_page_range_idx ON public.documents(page_range);
CREATE INDEX IF NOT EXISTS notebooks_user_id_idx ON public.notebooks(user_id);
CREATE INDEX IF NOT EXISTS documents_user_id_idx ON public.documents(user_id);
CREATE INDEX IF NOT EXISTS documents_notebook_document_idx ON public.documents(notebook_id, document_name);
CREATE INDEX IF NOT EXISTS document_processing_status_user_id_idx ON public.document_processing_status(user_id);
DROP INDEX IF EXISTS public.document_processing_status_notebook_document_uidx;
CREATE INDEX IF NOT EXISTS chat_sessions_notebook_id_idx ON public.chat_sessions(notebook_id);
CREATE INDEX IF NOT EXISTS chat_sessions_user_id_idx ON public.chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS chat_messages_session_id_idx ON public.chat_messages(session_id);

ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS documents_notebook_id_fkey;
ALTER TABLE public.documents
    ADD CONSTRAINT documents_notebook_id_fkey
    FOREIGN KEY (notebook_id) REFERENCES public.notebooks(id) ON DELETE CASCADE;

ALTER TABLE public.document_processing_status DROP CONSTRAINT IF EXISTS document_processing_status_notebook_id_fkey;
ALTER TABLE public.document_processing_status
    ADD CONSTRAINT document_processing_status_notebook_id_fkey
    FOREIGN KEY (notebook_id) REFERENCES public.notebooks(id) ON DELETE CASCADE;

ALTER TABLE public.chat_sessions DROP CONSTRAINT IF EXISTS chat_sessions_notebook_id_fkey;
ALTER TABLE public.chat_sessions
    ADD CONSTRAINT chat_sessions_notebook_id_fkey
    FOREIGN KEY (notebook_id) REFERENCES public.notebooks(id) ON DELETE CASCADE;

ALTER TABLE public.chat_messages DROP CONSTRAINT IF EXISTS chat_messages_session_id_fkey;
ALTER TABLE public.chat_messages
    ADD CONSTRAINT chat_messages_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES public.chat_sessions(id) ON DELETE CASCADE;

ALTER TABLE public.audio_overviews DROP CONSTRAINT IF EXISTS audio_overviews_notebook_id_fkey;
ALTER TABLE public.audio_overviews
    ADD CONSTRAINT audio_overviews_notebook_id_fkey
    FOREIGN KEY (notebook_id) REFERENCES public.notebooks(id) ON DELETE CASCADE;

ALTER TABLE public.slides DROP CONSTRAINT IF EXISTS slides_notebook_id_fkey;
ALTER TABLE public.slides
    ADD CONSTRAINT slides_notebook_id_fkey
    FOREIGN KEY (notebook_id) REFERENCES public.notebooks(id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS public.notebook_notes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    notebook_id UUID REFERENCES public.notebooks(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources JSONB DEFAULT '[]'::jsonb NOT NULL,
    document_names TEXT[] DEFAULT ARRAY[]::TEXT[] NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS notebook_notes_notebook_id_idx ON public.notebook_notes(notebook_id);
CREATE INDEX IF NOT EXISTS notebook_notes_user_id_idx ON public.notebook_notes(user_id);

ALTER TABLE public.notebook_notes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own notebook notes" ON public.notebook_notes;
DROP POLICY IF EXISTS "Users can insert own notebook notes" ON public.notebook_notes;
DROP POLICY IF EXISTS "Users can update own notebook notes" ON public.notebook_notes;
DROP POLICY IF EXISTS "Users can delete own notebook notes" ON public.notebook_notes;
DROP POLICY IF EXISTS "Service roles can manage notebook notes" ON public.notebook_notes;

CREATE POLICY "Users can view own notebook notes"
ON public.notebook_notes FOR SELECT TO authenticated
USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can insert own notebook notes"
ON public.notebook_notes FOR INSERT TO authenticated
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can update own notebook notes"
ON public.notebook_notes FOR UPDATE TO authenticated
USING ((select auth.uid()) = user_id)
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can delete own notebook notes"
ON public.notebook_notes FOR DELETE TO authenticated
USING ((select auth.uid()) = user_id);

CREATE POLICY "Service roles can manage notebook notes"
ON public.notebook_notes FOR ALL TO service_role
USING (true)
WITH CHECK (true);

-- Tighten existing RLS policies and avoid per-row auth.uid() init-plan warnings.
DROP POLICY IF EXISTS "Users can view own notebooks" ON public.notebooks;
DROP POLICY IF EXISTS "Users can insert own notebooks" ON public.notebooks;
DROP POLICY IF EXISTS "Users can update own notebooks" ON public.notebooks;
DROP POLICY IF EXISTS "Users can delete own notebooks" ON public.notebooks;

CREATE POLICY "Users can view own notebooks"
ON public.notebooks FOR SELECT TO authenticated
USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can insert own notebooks"
ON public.notebooks FOR INSERT TO authenticated
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can update own notebooks"
ON public.notebooks FOR UPDATE TO authenticated
USING ((select auth.uid()) = user_id)
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can delete own notebooks"
ON public.notebooks FOR DELETE TO authenticated
USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can view own documents" ON public.documents;
DROP POLICY IF EXISTS "Users can insert own documents" ON public.documents;
DROP POLICY IF EXISTS "Users can update own documents" ON public.documents;
DROP POLICY IF EXISTS "Users can delete own documents" ON public.documents;

CREATE POLICY "Users can view own documents"
ON public.documents FOR SELECT TO authenticated
USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can insert own documents"
ON public.documents FOR INSERT TO authenticated
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can update own documents"
ON public.documents FOR UPDATE TO authenticated
USING ((select auth.uid()) = user_id)
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can delete own documents"
ON public.documents FOR DELETE TO authenticated
USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can view processing status of own documents" ON public.document_processing_status;
DROP POLICY IF EXISTS "Users can insert processing status of own documents" ON public.document_processing_status;
DROP POLICY IF EXISTS "Users can update processing status of own documents" ON public.document_processing_status;
DROP POLICY IF EXISTS "Users can delete processing status of own documents" ON public.document_processing_status;

CREATE POLICY "Users can view processing status of own documents"
ON public.document_processing_status FOR SELECT TO authenticated
USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can insert processing status of own documents"
ON public.document_processing_status FOR INSERT TO authenticated
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can update processing status of own documents"
ON public.document_processing_status FOR UPDATE TO authenticated
USING ((select auth.uid()) = user_id)
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can delete processing status of own documents"
ON public.document_processing_status FOR DELETE TO authenticated
USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can view own chat sessions" ON public.chat_sessions;
DROP POLICY IF EXISTS "Users can insert own chat sessions" ON public.chat_sessions;
DROP POLICY IF EXISTS "Users can update own chat sessions" ON public.chat_sessions;
DROP POLICY IF EXISTS "Users can delete own chat sessions" ON public.chat_sessions;

CREATE POLICY "Users can view own chat sessions"
ON public.chat_sessions FOR SELECT TO authenticated
USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can insert own chat sessions"
ON public.chat_sessions FOR INSERT TO authenticated
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can update own chat sessions"
ON public.chat_sessions FOR UPDATE TO authenticated
USING ((select auth.uid()) = user_id)
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can delete own chat sessions"
ON public.chat_sessions FOR DELETE TO authenticated
USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can view own chat messages" ON public.chat_messages;
DROP POLICY IF EXISTS "Users can insert own chat messages" ON public.chat_messages;

CREATE POLICY "Users can view own chat messages"
ON public.chat_messages FOR SELECT TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.chat_sessions cs
        WHERE cs.id = chat_messages.session_id
          AND cs.user_id = (select auth.uid())
    )
);

CREATE POLICY "Users can insert own chat messages"
ON public.chat_messages FOR INSERT TO authenticated
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.chat_sessions cs
        WHERE cs.id = chat_messages.session_id
          AND cs.user_id = (select auth.uid())
    )
);

DROP FUNCTION IF EXISTS public.match_documents(vector, uuid, integer, text);
DROP FUNCTION IF EXISTS public.match_documents(halfvec, uuid, integer, text);

CREATE OR REPLACE FUNCTION public.match_documents(
    query_embedding halfvec(3072),
    target_notebook_id UUID,
    match_count INTEGER DEFAULT 5,
    filter_document TEXT DEFAULT NULL
)
RETURNS TABLE (
    id BIGINT,
    document_name TEXT,
    chunk_id INTEGER,
    content TEXT,
    metadata JSONB,
    pages INTEGER[],
    page_range TEXT,
    similarity DOUBLE PRECISION
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.document_name,
        d.chunk_id,
        d.content,
        d.metadata,
        d.pages,
        d.page_range,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM public.documents d
    WHERE d.notebook_id = target_notebook_id
      AND (filter_document IS NULL OR d.document_name = filter_document)
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.match_documents(halfvec, uuid, integer, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.match_documents(halfvec, uuid, integer, text) FROM anon;
REVOKE EXECUTE ON FUNCTION public.match_documents(halfvec, uuid, integer, text) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.match_documents(halfvec, uuid, integer, text) TO service_role;

-- Backend owns data access; browser clients should not use anon for user data tables.
REVOKE ALL ON public.notebooks FROM anon;
REVOKE ALL ON public.documents FROM anon;
REVOKE ALL ON public.document_processing_status FROM anon;
REVOKE ALL ON public.chat_sessions FROM anon;
REVOKE ALL ON public.chat_messages FROM anon;
REVOKE ALL ON public.notebook_notes FROM anon;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.notebooks TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.documents TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.document_processing_status TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_sessions TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_messages TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.notebook_notes TO authenticated;

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('pdfs', 'pdfs', false, 52428800, ARRAY['application/pdf']::text[])
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS "Service role can manage notebook PDFs" ON storage.objects;
CREATE POLICY "Service role can manage notebook PDFs"
ON storage.objects FOR ALL TO service_role
USING (bucket_id = 'pdfs')
WITH CHECK (bucket_id = 'pdfs');
