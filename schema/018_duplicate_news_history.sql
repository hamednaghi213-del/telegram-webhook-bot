BEGIN;

-- =========================================================
-- DUPLICATE NEWS HISTORY
-- =========================================================
--
-- One row represents one logical news publication.
-- It is NOT one row per Telegram/Bale destination.
--
-- Duplicate checks are scoped by media_identity_id.
-- Access is server-side only through service_role.
-- =========================================================

CREATE TABLE IF NOT EXISTS public.duplicate_news_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    media_identity_id BIGINT NOT NULL
        REFERENCES public.media_identities(id)
        ON DELETE CASCADE,

    actor_user_id BIGINT
        REFERENCES public.users(id)
        ON DELETE SET NULL,

    source_key TEXT NOT NULL,

    content_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    fingerprint TEXT NOT NULL,

    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT duplicate_news_history_source_unique
        UNIQUE (media_identity_id, source_key),

    CONSTRAINT duplicate_news_history_fingerprint_not_empty
        CHECK (length(fingerprint) > 0)
);

-- Fast exact-duplicate lookup inside one Media Identity.
CREATE INDEX IF NOT EXISTS
    duplicate_news_history_media_fingerprint_idx
ON public.duplicate_news_history (
    media_identity_id,
    fingerprint
);

-- Fast recent-history lookup for near-duplicate comparison.
CREATE INDEX IF NOT EXISTS
    duplicate_news_history_media_published_idx
ON public.duplicate_news_history (
    media_identity_id,
    published_at DESC
);

-- ---------------------------------------------------------
-- SECURITY
-- ---------------------------------------------------------
--
-- This history contains cross-user publication information.
-- It must not be directly readable or writable with the public
-- anon/authenticated Supabase keys.
--
-- The backend already has a dedicated service-role client.
-- Duplicate Guard will use that client in a later stage.
-- ---------------------------------------------------------

ALTER TABLE public.duplicate_news_history
ENABLE ROW LEVEL SECURITY;

REVOKE ALL
ON TABLE public.duplicate_news_history
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON SEQUENCE public.duplicate_news_history_id_seq
FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.duplicate_news_history
TO service_role;

GRANT USAGE, SELECT
ON SEQUENCE public.duplicate_news_history_id_seq
TO service_role;

NOTIFY pgrst, 'reload schema';

COMMIT;
