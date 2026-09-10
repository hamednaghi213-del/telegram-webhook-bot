-- =========================================================
-- 025_translation_review_state_alignment.sql
-- Align persistent translation schema with TranslationState API
-- =========================================================

ALTER TABLE public.translation_reviews
    ADD COLUMN IF NOT EXISTS source_kind TEXT NOT NULL DEFAULT 'message';

ALTER TABLE public.translation_reviews
    ADD COLUMN IF NOT EXISTS source_key TEXT NOT NULL DEFAULT '';

ALTER TABLE public.translation_reviews
    ADD COLUMN IF NOT EXISTS target_language_code TEXT NOT NULL DEFAULT '';


-- Preserve any value already stored through the original
-- 024 content_kind column.
UPDATE public.translation_reviews
SET source_kind = content_kind
WHERE
    (source_kind IS NULL OR source_kind = '' OR source_kind = 'message')
    AND content_kind IS NOT NULL
    AND content_kind <> '';


CREATE INDEX IF NOT EXISTS
    idx_translation_reviews_source_key
ON public.translation_reviews (
    source_key
)
WHERE source_key <> '';


COMMENT ON COLUMN public.translation_reviews.source_kind IS
'Origin workflow/content kind used by TranslationState and publication handoff.';

COMMENT ON COLUMN public.translation_reviews.source_key IS
'Stable logical source key carried through translation into the shared publication workflow.';

COMMENT ON COLUMN public.translation_reviews.target_language_code IS
'Normalized UI/application language code for the selected translation target.';
