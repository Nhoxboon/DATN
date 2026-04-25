-- Create document processing status table
CREATE TABLE IF NOT EXISTS document_processing_status (
    document_name TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    total_chunks INTEGER,
    processed_chunks INTEGER DEFAULT 0,
    task_id TEXT,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Create index for status queries
CREATE INDEX IF NOT EXISTS document_processing_status_status_idx ON document_processing_status(status);

-- Create index for task_id
CREATE INDEX IF NOT EXISTS document_processing_status_task_id_idx ON document_processing_status(task_id);

-- Enable RLS
ALTER TABLE document_processing_status ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Allow service role full access to processing status"
ON document_processing_status
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Allow authenticated users to read their processing status
CREATE POLICY "Allow authenticated read access to processing status"
ON document_processing_status
FOR SELECT
TO authenticated
USING (true);
