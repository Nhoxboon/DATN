-- 1. Enable specific extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create the Notebooks table
-- Notebooks replace the concept of a single "project", allowing multiple notebooks per user.
CREATE TABLE IF NOT EXISTS public.notebooks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Create the Documents table (combines chunks and vector embeddings like pdp8-rag)
CREATE TABLE IF NOT EXISTS public.documents (
    id BIGSERIAL PRIMARY KEY,
    notebook_id UUID REFERENCES public.notebooks(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    document_name TEXT NOT NULL,
    chunk_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(768),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS documents_embedding_idx
ON public.documents USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create indeces for faster lookups
CREATE INDEX IF NOT EXISTS documents_name_idx ON public.documents(document_name);
CREATE INDEX IF NOT EXISTS documents_notebook_id_idx ON public.documents(notebook_id);

-- 4. Create Document Processing Status table (adapted from pdp8-rag)
CREATE TABLE IF NOT EXISTS public.document_processing_status (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    notebook_id UUID REFERENCES public.notebooks(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    document_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    total_chunks INTEGER,
    processed_chunks INTEGER DEFAULT 0,
    task_id TEXT,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(notebook_id, document_name)
);

-- Create index for status queries
CREATE INDEX IF NOT EXISTS document_processing_status_status_idx ON public.document_processing_status(status);
CREATE INDEX IF NOT EXISTS document_processing_status_task_id_idx ON public.document_processing_status(task_id);

-- 5. Media Generation: Audio Overviews and Slides
CREATE TYPE media_status_enum AS ENUM ('pending', 'processing', 'completed', 'failed');

-- Table for Audio Overviews (mp3)
CREATE TABLE IF NOT EXISTS public.audio_overviews (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    notebook_id UUID REFERENCES public.notebooks(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    storage_path TEXT, -- URL or path to the generated .mp3 file
    status media_status_enum DEFAULT 'pending' NOT NULL,
    metadata JSONB, -- For storing duration, speakers config, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Table for Slides / Presentations (pdf)
CREATE TABLE IF NOT EXISTS public.slides (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    notebook_id UUID REFERENCES public.notebooks(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    storage_path TEXT, -- URL or path to the generated .pdf file
    status media_status_enum DEFAULT 'pending' NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 6. Optionally storing chat history in Database
CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    notebook_id UUID REFERENCES public.notebooks(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.chat_messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id UUID REFERENCES public.chat_sessions(id) ON DELETE CASCADE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    sources JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 7. Setup Row Level Security (RLS)

-- Notebooks RLS
ALTER TABLE public.notebooks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own notebooks" ON public.notebooks FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own notebooks" ON public.notebooks FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own notebooks" ON public.notebooks FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own notebooks" ON public.notebooks FOR DELETE USING (auth.uid() = user_id);

-- Documents RLS
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own documents" ON public.documents FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own documents" ON public.documents FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own documents" ON public.documents FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own documents" ON public.documents FOR DELETE USING (auth.uid() = user_id);
CREATE POLICY "Service roles can manage documents" ON public.documents FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Document Processing Status RLS
ALTER TABLE public.document_processing_status ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view processing status of own documents" ON public.document_processing_status FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert processing status of own documents" ON public.document_processing_status FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update processing status of own documents" ON public.document_processing_status FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete processing status of own documents" ON public.document_processing_status FOR DELETE USING (auth.uid() = user_id);
CREATE POLICY "Service roles can manage processing status" ON public.document_processing_status FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Audio Overviews RLS
ALTER TABLE public.audio_overviews ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own audio overviews" ON public.audio_overviews FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own audio overviews" ON public.audio_overviews FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own audio overviews" ON public.audio_overviews FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own audio overviews" ON public.audio_overviews FOR DELETE USING (auth.uid() = user_id);
CREATE POLICY "Service roles can manage audio overviews" ON public.audio_overviews FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Slides RLS
ALTER TABLE public.slides ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own slides" ON public.slides FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own slides" ON public.slides FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own slides" ON public.slides FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own slides" ON public.slides FOR DELETE USING (auth.uid() = user_id);
CREATE POLICY "Service roles can manage slides" ON public.slides FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Chat Sessions RLS
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own chat sessions" ON public.chat_sessions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own chat sessions" ON public.chat_sessions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own chat sessions" ON public.chat_sessions FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own chat sessions" ON public.chat_sessions FOR DELETE USING (auth.uid() = user_id);

-- Chat Messages RLS
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own chat messages" ON public.chat_messages 
FOR SELECT USING (
    EXISTS (
        SELECT 1 FROM public.chat_sessions cs
        WHERE cs.id = session_id AND cs.user_id = auth.uid()
    )
);
CREATE POLICY "Users can insert own chat messages" ON public.chat_messages 
FOR INSERT WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.chat_sessions cs
        WHERE cs.id = session_id AND cs.user_id = auth.uid()
    )
);

-- 8. Vector Search Function
-- Updated search function to scope by notebook_id
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(768),
    target_notebook_id UUID,
    match_count INT DEFAULT 5,
    filter_document TEXT DEFAULT NULL
)
RETURNS TABLE (
    id BIGINT,
    document_name TEXT,
    chunk_id INTEGER,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.document_name,
        d.chunk_id,
        d.content,
        d.metadata,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM public.documents d
    WHERE d.notebook_id = target_notebook_id
      AND (filter_document IS NULL OR d.document_name = filter_document)
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
