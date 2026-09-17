-- =========================================================
-- 027 — B7: PERSISTENT EDITORIAL PENDING REVIEWS
-- =========================================================
--
-- Durable storage for Editorial Pending reviews so that pending
-- summaries survive process restart and deploy.
--
-- SEMANTICS CONTRACT (must stay in sync with core/editorial_pending.py):
--
-- - review_id is the application-generated 16-hex-char id.
-- - status uses exactly the lifecycle values the in-memory store
--   uses today:
--     pending, published_summary, published_original,
--     cancelled, expired
-- - metadata is the free-form review metadata dict (admin
--   instruction waiting flags live there today).
-- - expires_at is the review TTL (DEFAULT_PENDING_TTL_SECONDS).
-- - action_claim_owner / action_claim_expires_at form the atomic
--   cross-worker action claim (approve / regenerate / cancel must
--   run exactly once).
--
-- The migration is additive and rollback-safe: no existing table,
-- RPC or view is altered or dropped.
-- =========================================================

BEGIN;

-- =========================================================
-- TABLE
-- =========================================================

CREATE TABLE IF NOT EXISTS public.editorial_pending_reviews (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    review_id TEXT NOT NULL,

    user_id BIGINT NOT NULL,

    content_type TEXT NOT NULL,

    original_text TEXT NOT NULL DEFAULT '',

    current_summary TEXT NOT NULL DEFAULT '',

    regeneration_count INTEGER NOT NULL DEFAULT 0
        CHECK (regeneration_count >= 0),

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'published_summary',
                'published_original',
                'cancelled',
                'expired'
            )
        ),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(metadata) = 'object'),

    expires_at TIMESTAMPTZ,

    -- Atomic cross-worker action claim.
    action_claim_owner TEXT,
    action_claim_expires_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT editorial_pending_reviews_unique
        UNIQUE (review_id)
);


-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX IF NOT EXISTS
    editorial_pending_reviews_user_status_idx
ON public.editorial_pending_reviews (
    user_id,
    status
);

CREATE INDEX IF NOT EXISTS
    editorial_pending_reviews_expires_idx
ON public.editorial_pending_reviews (
    expires_at
);


-- =========================================================
-- UPDATED_AT TRIGGER
-- =========================================================

CREATE OR REPLACE FUNCTION public.set_editorial_pending_reviews_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS
    editorial_pending_reviews_updated_at
ON public.editorial_pending_reviews;

CREATE TRIGGER editorial_pending_reviews_updated_at
BEFORE UPDATE
ON public.editorial_pending_reviews
FOR EACH ROW
EXECUTE FUNCTION public.set_editorial_pending_reviews_updated_at();


-- =========================================================
-- ATOMIC ACTION CLAIM RPC
-- =========================================================
--
-- claim_editorial_review_action:
--
-- - Cross-worker "exactly once" action claiming for approve /
--   regenerate / cancel / mark-published transitions.
-- - SELECT ... FOR UPDATE row lock plus an action claim lease
--   (action_claim_owner / action_claim_expires_at) guarantees only
--   one worker executes the action for a given expected status.
-- - p_expected_status guards against racing transitions: a claim
--   is granted only while the review is still in the expected
--   lifecycle state.
-- - Expired claims are reclaimable (crash/deploy recovery).
-- - Claiming does NOT perform the action itself; the application
--   performs the transition and then records it via the normal
--   update functions.
-- =========================================================

CREATE OR REPLACE FUNCTION public.claim_editorial_review_action(
    p_review_id TEXT,
    p_expected_status TEXT DEFAULT 'pending',
    p_claim_owner TEXT DEFAULT NULL,
    p_claim_seconds INTEGER DEFAULT 120
)
RETURNS TABLE (
    claimed BOOLEAN,
    editorial_pending_review_id BIGINT,
    current_status TEXT,
    regeneration_count INTEGER,
    current_claim_expires_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_id BIGINT;
    v_status TEXT;
    v_regeneration_count INTEGER;
    v_claim_expires_at TIMESTAMPTZ;
    v_now TIMESTAMPTZ := NOW();
    v_claim_seconds INTEGER := GREATEST(
        30,
        LEAST(
            COALESCE(p_claim_seconds, 120),
            900
        )
    );
BEGIN
    IF NULLIF(BTRIM(COALESCE(p_review_id, '')), '') IS NULL THEN
        RAISE EXCEPTION 'review_id is required';
    END IF;

    IF NULLIF(BTRIM(COALESCE(p_expected_status, '')), '') IS NULL THEN
        RAISE EXCEPTION 'expected_status is required';
    END IF;

    SELECT
        epr.id,
        epr.status,
        epr.regeneration_count,
        epr.action_claim_expires_at
    INTO
        v_id,
        v_status,
        v_regeneration_count,
        v_claim_expires_at
    FROM public.editorial_pending_reviews AS epr
    WHERE epr.review_id = p_review_id
    FOR UPDATE;

    IF v_id IS NULL THEN
        -- Unknown review (already deleted by cleanup, or created on
        -- a worker whose dual-write failed). Soft no.
        RETURN QUERY
        SELECT
            FALSE,
            NULL::BIGINT,
            NULL::TEXT,
            NULL::INTEGER,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    IF v_status <> p_expected_status THEN
        RETURN QUERY
        SELECT
            FALSE,
            v_id,
            v_status,
            v_regeneration_count,
            v_claim_expires_at;
        RETURN;
    END IF;

    -- Active claim held by another worker. Expired claims are
    -- reclaimable.
    IF (
        v_claim_expires_at IS NOT NULL
        AND v_claim_expires_at > v_now
    ) THEN
        RETURN QUERY
        SELECT
            FALSE,
            v_id,
            v_status,
            v_regeneration_count,
            v_claim_expires_at;
        RETURN;
    END IF;

    UPDATE public.editorial_pending_reviews AS epr
    SET
        action_claim_owner = NULLIF(
            BTRIM(COALESCE(p_claim_owner, '')),
            ''
        ),
        action_claim_expires_at =
            v_now
            + make_interval(
                secs => v_claim_seconds
            )
    WHERE epr.id = v_id
    RETURNING
        epr.action_claim_expires_at
    INTO
        v_claim_expires_at;

    RETURN QUERY
    SELECT
        TRUE,
        v_id,
        v_status,
        v_regeneration_count,
        v_claim_expires_at;
END;
$$;


-- =========================================================
-- SECURITY
-- =========================================================

ALTER TABLE public.editorial_pending_reviews
ENABLE ROW LEVEL SECURITY;


REVOKE ALL
ON TABLE public.editorial_pending_reviews
FROM PUBLIC, anon, authenticated;


REVOKE ALL
ON SEQUENCE public.editorial_pending_reviews_id_seq
FROM PUBLIC, anon, authenticated;


GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.editorial_pending_reviews
TO service_role;


GRANT USAGE, SELECT
ON SEQUENCE public.editorial_pending_reviews_id_seq
TO service_role;


REVOKE ALL
ON FUNCTION public.claim_editorial_review_action(
    TEXT,
    TEXT,
    TEXT,
    INTEGER
)
FROM PUBLIC, anon, authenticated;


GRANT EXECUTE
ON FUNCTION public.claim_editorial_review_action(
    TEXT,
    TEXT,
    TEXT,
    INTEGER
)
TO service_role;


-- Trigger function must not be callable by client roles.
REVOKE ALL
ON FUNCTION public.set_editorial_pending_reviews_updated_at()
FROM PUBLIC, anon, authenticated;


GRANT EXECUTE
ON FUNCTION public.set_editorial_pending_reviews_updated_at()
TO service_role;


NOTIFY pgrst, 'reload schema';

COMMIT;
