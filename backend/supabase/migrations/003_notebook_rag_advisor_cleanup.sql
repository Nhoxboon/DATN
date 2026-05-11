-- Cleanup follow-up from Supabase advisors after notebook RAG migration.

DROP INDEX IF EXISTS public.document_processing_status_notebook_document_uidx;

CREATE INDEX IF NOT EXISTS audio_overviews_notebook_id_idx ON public.audio_overviews(notebook_id);
CREATE INDEX IF NOT EXISTS audio_overviews_user_id_idx ON public.audio_overviews(user_id);
CREATE INDEX IF NOT EXISTS slides_notebook_id_idx ON public.slides(notebook_id);
CREATE INDEX IF NOT EXISTS slides_user_id_idx ON public.slides(user_id);

DROP POLICY IF EXISTS "Users can view own audio overviews" ON public.audio_overviews;
DROP POLICY IF EXISTS "Users can insert own audio overviews" ON public.audio_overviews;
DROP POLICY IF EXISTS "Users can update own audio overviews" ON public.audio_overviews;
DROP POLICY IF EXISTS "Users can delete own audio overviews" ON public.audio_overviews;

CREATE POLICY "Users can view own audio overviews"
ON public.audio_overviews FOR SELECT TO authenticated
USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can insert own audio overviews"
ON public.audio_overviews FOR INSERT TO authenticated
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can update own audio overviews"
ON public.audio_overviews FOR UPDATE TO authenticated
USING ((select auth.uid()) = user_id)
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can delete own audio overviews"
ON public.audio_overviews FOR DELETE TO authenticated
USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can view own slides" ON public.slides;
DROP POLICY IF EXISTS "Users can insert own slides" ON public.slides;
DROP POLICY IF EXISTS "Users can update own slides" ON public.slides;
DROP POLICY IF EXISTS "Users can delete own slides" ON public.slides;

CREATE POLICY "Users can view own slides"
ON public.slides FOR SELECT TO authenticated
USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can insert own slides"
ON public.slides FOR INSERT TO authenticated
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can update own slides"
ON public.slides FOR UPDATE TO authenticated
USING ((select auth.uid()) = user_id)
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can delete own slides"
ON public.slides FOR DELETE TO authenticated
USING ((select auth.uid()) = user_id);
