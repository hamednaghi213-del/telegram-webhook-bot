BEGIN;

ALTER TABLE public.publication_destinations
    ADD COLUMN IF NOT EXISTS target_language_code TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS translation_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;