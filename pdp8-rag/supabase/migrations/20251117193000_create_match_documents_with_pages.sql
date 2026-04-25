-- Drop existing match_documents function
DROP FUNCTION IF EXISTS match_documents(halfvec, integer, text);
DROP FUNCTION IF EXISTS match_documents(halfvec, integer);
DROP FUNCTION IF EXISTS match_documents;

-- Create match_documents function with page information support
CREATE FUNCTION match_documents(
    query_embedding halfvec(3072),
    match_count integer DEFAULT 5,
    filter_document text DEFAULT NULL
)
RETURNS TABLE (
    id bigint,
    document_name text,
    chunk_id integer,
    content text,
    metadata jsonb,
    pages integer[],
    page_range text,
    similarity float
)
LANGUAGE plpgsql
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
    FROM documents d
    WHERE (filter_document IS NULL OR d.document_name = filter_document)
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
