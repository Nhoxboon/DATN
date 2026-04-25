-- Create storage bucket for PDFs
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'pdfs',
    'pdfs',
    false,
    52428800, -- 50MB limit
    ARRAY['application/pdf']::text[]
)
ON CONFLICT (id) DO NOTHING;

-- Storage policies for pdfs bucket
-- Policy: Allow authenticated users to upload PDFs
CREATE POLICY "Allow authenticated users to upload PDFs"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
    bucket_id = 'pdfs'
);

-- Policy: Allow users to read PDFs
CREATE POLICY "Allow users to read PDFs"
ON storage.objects
FOR SELECT
TO authenticated
USING (
    bucket_id = 'pdfs'
);

-- Policy: Allow public read access to PDFs
CREATE POLICY "Allow public read access to PDFs"
ON storage.objects
FOR SELECT
TO anon
USING (
    bucket_id = 'pdfs'
);

-- Policy: Allow users to delete PDFs
CREATE POLICY "Allow users to delete PDFs"
ON storage.objects
FOR DELETE
TO authenticated
USING (
    bucket_id = 'pdfs'
);

-- Policy: Allow service role full access
CREATE POLICY "Allow service role full access to PDFs"
ON storage.objects
FOR ALL
TO service_role
USING (bucket_id = 'pdfs')
WITH CHECK (bucket_id = 'pdfs');
