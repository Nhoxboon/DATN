-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create documents table
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    document_name TEXT NOT NULL,
    chunk_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(768),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS documents_embedding_idx
ON documents USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create index for document_name
CREATE INDEX IF NOT EXISTS documents_name_idx ON documents(document_name);

-- Enable RLS
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

-- Create RLS policies
-- Policy: Allow anonymous users to read all documents
CREATE POLICY "Allow public read access"
ON documents
FOR SELECT
TO anon
USING (true);

-- Policy: Allow authenticated users to read all documents
CREATE POLICY "Allow authenticated read access"
ON documents
FOR SELECT
TO authenticated
USING (true);

-- Policy: Allow service role to insert documents
CREATE POLICY "Allow service role to insert"
ON documents
FOR INSERT
TO service_role
WITH CHECK (true);

-- Policy: Allow authenticated users to insert documents
CREATE POLICY "Allow authenticated insert"
ON documents
FOR INSERT
TO authenticated
WITH CHECK (true);

-- Policy: Allow service role to update documents
CREATE POLICY "Allow service role to update"
ON documents
FOR UPDATE
TO service_role
USING (true);

-- Policy: Allow service role to delete documents
CREATE POLICY "Allow service role to delete"
ON documents
FOR DELETE
TO service_role
USING (true);

-- Create function for similarity search
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(768),
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
        documents.id,
        documents.document_name,
        documents.chunk_id,
        documents.content,
        documents.metadata,
        1 - (documents.embedding <=> query_embedding) AS similarity
    FROM documents
    WHERE
        CASE
            WHEN filter_document IS NOT NULL THEN documents.document_name = filter_document
            ELSE TRUE
        END
    ORDER BY documents.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
