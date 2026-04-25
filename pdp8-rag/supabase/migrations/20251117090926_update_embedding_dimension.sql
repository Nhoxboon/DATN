-- Drop existing index
DROP INDEX IF EXISTS documents_embedding_idx;

-- Alter the embedding column to use halfvec with 3072 dimensions
ALTER TABLE documents
ALTER COLUMN embedding TYPE halfvec(3072);

-- Recreate index with HNSW using halfvec (supports higher dimensions with lower memory)
CREATE INDEX documents_embedding_idx
ON documents USING hnsw (embedding halfvec_cosine_ops);

-- Update match_documents function to use halfvec(3072)
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding halfvec(3072),
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
