-- Storage bucket for generated notebook slide deck PDFs.

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('slide-decks', 'slide-decks', false, 52428800, ARRAY['application/pdf']::text[])
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS "Service role can manage notebook slide decks" ON storage.objects;
CREATE POLICY "Service role can manage notebook slide decks"
ON storage.objects FOR ALL TO service_role
USING (bucket_id = 'slide-decks')
WITH CHECK (bucket_id = 'slide-decks');
