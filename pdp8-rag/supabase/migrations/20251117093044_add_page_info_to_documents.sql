-- Add page information columns to documents table
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS pages INTEGER[],
ADD COLUMN IF NOT EXISTS page_range TEXT;

-- Create index on page_range for faster filtering
CREATE INDEX IF NOT EXISTS documents_page_range_idx ON documents(page_range);
