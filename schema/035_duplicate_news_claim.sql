BEGIN;

-- =========================================================
-- 034 — ATOMIC DUPLICATE NEWS CLAIM
-- =========================================================
--
-- Prevent two different source updates carrying the same exact
-- news content from publishing concurrently to the same
-- canonical Media Identity.
--
-- duplicate_news_history remains the durable publication history.
-- This table is only an in-flight reservation layer.
-- =========================================================

CREATE TABLE IF NOT EXISTS public.duplicate_news_claims (
    media_identity_id BIGINT NOT NULL
        REFERENCES public.media_identities(id)
        ON DELETE CASCADE,

    fingerprint TEXT NOT NULL,

    source_key TEXT NOT NULL,

    actor_user_id BIGINT
        REFERENCES public.users(id)
        ON DELETE SET NULL,

    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    lease_expires_at TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (
        media_identity_id,
        fingerprint
    ),

    CONSTRAINT duplicate_news_claims_fingerprint_not_empty
        CHECK (length(fingerprint) > 0),

    CONSTRAINT duplicate_news_claims_source_key_not_empty
        CHECK (length(source_key) > 0)
);


CREATE INDEX IF NOT EXISTS
duplicate_news_claims_lease_expires_idx
ON public.duplicate_news_claims (
    lease_expires_at
);


-- =========================================================
-- CLAIM
-- =========================================================
--
-- Exactly one live owner may hold
-- (media_identity_id, fingerprint).
--
-- Same source_key is allowed to re-enter and refresh its lease.
-- An expired lease may be reclaimed by another source.
-- =========================================================

CREATE OR REPLACE FUNCTION public.claim_duplicate_news_publication(
    p_media_identity_id BIGINT,
    p_fingerprint TEXT,
    p_source_key TEXT,
    p_actor_user_id BIGINT DEFAULT NULL,
    p_lease_seconds INTEGER DEFAULT 300
)
RETURNS TABLE (
    claimed BOOLEAN,
    owner_source_key TEXT,
    lease_expires_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_existing public.duplicate_news_claims%ROWTYPE;
    v_lease_seconds INTEGER;
    v_expires_at TIMESTAMPTZ;
BEGIN
    IF p_media_identity_id IS NULL THEN
        RAISE EXCEPTION
            'media_identity_id is required';
    END IF;

    IF COALESCE(length(trim(p_fingerprint)), 0) = 0 THEN
        RAISE EXCEPTION
            'fingerprint is required';
    END IF;

    IF COALESCE(length(trim(p_source_key)), 0) = 0 THEN
        RAISE EXCEPTION
            'source_key is required';
    END IF;

    v_lease_seconds :=
        GREATEST(
            30,
            LEAST(
                COALESCE(p_lease_seconds, 300),
                3600
            )
        );

    v_expires_at :=
        NOW()
        + make_interval(
            secs => v_lease_seconds
        );

    INSERT INTO public.duplicate_news_claims (
        media_identity_id,
        fingerprint,
        source_key,
        actor_user_id,
        claimed_at,
        lease_expires_at
    )
    VALUES (
        p_media_identity_id,
        p_fingerprint,
        p_source_key,
        p_actor_user_id,
        NOW(),
        v_expires_at
    )
    ON CONFLICT (
        media_identity_id,
        fingerprint
    )
    DO NOTHING;

    IF FOUND THEN
        RETURN QUERY
        SELECT
            TRUE,
            p_source_key,
            v_expires_at;

        RETURN;
    END IF;

    SELECT *
    INTO v_existing
    FROM public.duplicate_news_claims
    WHERE media_identity_id =
        p_media_identity_id
      AND fingerprint =
        p_fingerprint
    FOR UPDATE;

    IF NOT FOUND THEN
        -- Extremely narrow race:
        -- conflicting row disappeared between INSERT
        -- and SELECT. Retry the claim once.
        INSERT INTO public.duplicate_news_claims (
            media_identity_id,
            fingerprint,
            source_key,
            actor_user_id,
            claimed_at,
            lease_expires_at
        )
        VALUES (
            p_media_identity_id,
            p_fingerprint,
            p_source_key,
            p_actor_user_id,
            NOW(),
            v_expires_at
        )
        ON CONFLICT (
            media_identity_id,
            fingerprint
        )
        DO NOTHING;

        IF FOUND THEN
            RETURN QUERY
            SELECT
                TRUE,
                p_source_key,
                v_expires_at;

            RETURN;
        END IF;

        SELECT *
        INTO v_existing
        FROM public.duplicate_news_claims
        WHERE media_identity_id =
            p_media_identity_id
          AND fingerprint =
            p_fingerprint
        FOR UPDATE;
    END IF;

    IF (
        v_existing.source_key = p_source_key
        OR v_existing.lease_expires_at <= NOW()
    ) THEN

        UPDATE public.duplicate_news_claims
        SET
            source_key = p_source_key,
            actor_user_id = p_actor_user_id,
            claimed_at = NOW(),
            lease_expires_at = v_expires_at
        WHERE media_identity_id =
            p_media_identity_id
          AND fingerprint =
            p_fingerprint;

        RETURN QUERY
        SELECT
            TRUE,
            p_source_key,
            v_expires_at;

        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        FALSE,
        v_existing.source_key,
        v_existing.lease_expires_at;
END;
$$;


-- =========================================================
-- FINALIZE
-- =========================================================
--
-- Persist successful publication history and release the
-- in-flight reservation in the SAME database transaction.
--
-- Only the source that owns the live claim may finalize it.
-- =========================================================

CREATE OR REPLACE FUNCTION public.finalize_duplicate_news_publication(
    p_media_identity_id BIGINT,
    p_fingerprint TEXT,
    p_source_key TEXT,
    p_actor_user_id BIGINT,
    p_content_text TEXT,
    p_normalized_text TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_owner_source_key TEXT;
BEGIN
    SELECT source_key
    INTO v_owner_source_key
    FROM public.duplicate_news_claims
    WHERE media_identity_id =
        p_media_identity_id
      AND fingerprint =
        p_fingerprint
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF v_owner_source_key <> p_source_key THEN
        RETURN FALSE;
    END IF;

    INSERT INTO public.duplicate_news_history (
        media_identity_id,
        actor_user_id,
        source_key,
        content_text,
        normalized_text,
        fingerprint,
        published_at
    )
    VALUES (
        p_media_identity_id,
        p_actor_user_id,
        p_source_key,
        COALESCE(p_content_text, ''),
        COALESCE(p_normalized_text, ''),
        p_fingerprint,
        NOW()
    )
    ON CONFLICT (
        media_identity_id,
        source_key
    )
    DO UPDATE SET
        actor_user_id =
            EXCLUDED.actor_user_id,
        content_text =
            EXCLUDED.content_text,
        normalized_text =
            EXCLUDED.normalized_text,
        fingerprint =
            EXCLUDED.fingerprint,
        published_at =
            EXCLUDED.published_at;

    DELETE FROM public.duplicate_news_claims
    WHERE media_identity_id =
        p_media_identity_id
      AND fingerprint =
        p_fingerprint
      AND source_key =
        p_source_key;

    RETURN TRUE;
END;
$$;


-- =========================================================
-- RELEASE
-- =========================================================
--
-- Used only when the publication produced no successful
-- destination delivery.
--
-- A source may release only its own reservation.
-- =========================================================

CREATE OR REPLACE FUNCTION public.release_duplicate_news_publication(
    p_media_identity_id BIGINT,
    p_fingerprint TEXT,
    p_source_key TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_deleted INTEGER;
BEGIN
    DELETE FROM public.duplicate_news_claims
    WHERE media_identity_id =
        p_media_identity_id
      AND fingerprint =
        p_fingerprint
      AND source_key =
        p_source_key;

    GET DIAGNOSTICS
        v_deleted = ROW_COUNT;

    RETURN v_deleted > 0;
END;
$$;


-- =========================================================
-- SECURITY
-- =========================================================

ALTER TABLE public.duplicate_news_claims
ENABLE ROW LEVEL SECURITY;

REVOKE ALL
ON TABLE public.duplicate_news_claims
FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.duplicate_news_claims
TO service_role;


REVOKE ALL
ON FUNCTION public.claim_duplicate_news_publication(
    BIGINT,
    TEXT,
    TEXT,
    BIGINT,
    INTEGER
)
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON FUNCTION public.finalize_duplicate_news_publication(
    BIGINT,
    TEXT,
    TEXT,
    BIGINT,
    TEXT,
    TEXT
)
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON FUNCTION public.release_duplicate_news_publication(
    BIGINT,
    TEXT,
    TEXT
)
FROM PUBLIC, anon, authenticated;


GRANT EXECUTE
ON FUNCTION public.claim_duplicate_news_publication(
    BIGINT,
    TEXT,
    TEXT,
    BIGINT,
    INTEGER
)
TO service_role;

GRANT EXECUTE
ON FUNCTION public.finalize_duplicate_news_publication(
    BIGINT,
    TEXT,
    TEXT,
    BIGINT,
    TEXT,
    TEXT
)
TO service_role;

GRANT EXECUTE
ON FUNCTION public.release_duplicate_news_publication(
    BIGINT,
    TEXT,
    TEXT
)
TO service_role;


NOTIFY pgrst, 'reload schema';

COMMIT;