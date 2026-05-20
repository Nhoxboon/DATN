-- Storage bucket for generated notebook audio overviews.

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('audio-overviews', 'audio-overviews', false, 104857600, ARRAY['audio/mp4']::text[])
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS "Service role can manage notebook audio overviews" ON storage.objects;
CREATE POLICY "Service role can manage notebook audio overviews"
ON storage.objects FOR ALL TO service_role
USING (bucket_id = 'audio-overviews')
WITH CHECK (bucket_id = 'audio-overviews');
