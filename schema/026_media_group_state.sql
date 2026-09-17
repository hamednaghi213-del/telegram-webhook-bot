-- =========================================================
-- 026 — B6: PERSISTENT MEDIA GROUP STATE
-- =========================================================
--
-- Durable storage for Telegram album (media group) accumulation,
-- generation tracking and processing leases, so that an album can
-- be reconstructed after a process restart or deploy.
--
-- SEMANTICS CONTRACT (must stay in sync with core/media_handler.py):
--
-- - Identity scope: (chat_id, media_group_id) — the same key the
--   in-memory store uses for pending_groups.
-- - Lifecycle `state` uses exactly the values the in-memory state
--   machine uses today:
--     collecting, leased, publishing, editorial_pending,
--     duplicate_pending, retry_pending, published, failed_terminal
-- - generation / published_generation / timer_generation /
--   leased_generation / delivery_generation mirror the in-memory
--   counters; delivery_generation is part of the publication
--   source_key (tg:{chat}:album:{id}:generation:{n}).
-- - attempt_count is capped at 5 (MEDIA_GROUP_MAX_RETRIES) and is
--   reset by the application when a new delivery_generation starts.
-- - Claiming a generation takes a processing lease only. It NEVER
--   marks a generation published and never mutates content
--   generations or ordering.
--
-- The table is additive and rollback-safe: no existing table, RPC
-- or view is altered or dropped.
-- =========================================================

BEGIN;

-- =========================================================
-- TABLE
-- =========================================================

CREATE TABLE IF NOT EXISTS public.media_group_state (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- -----------------------------------------------------
    -- IDENTITY (scoped exactly like the in-memory store)
    -- -----------------------------------------------------

    chat_id BIGINT NOT NULL,

    media_group_id TEXT NOT NULL,

    -- -----------------------------------------------------
    -- LIFECYCLE
    -- -----------------------------------------------------

    state TEXT NOT NULL DEFAULT 'collecting'
        CHECK (
            state IN (
                'collecting',
                'leased',
                'publishing',
                'editorial_pending',
                'duplicate_pending',
                'retry_pending',
                'published',
                'failed_terminal'
            )
        ),

    -- -----------------------------------------------------
    -- CONTENT (ordered album items + Telegram payloads)
    --
    -- items: JSONB array in arrival order. Each element mirrors
    -- one entry of the in-memory group["files"] list:
    --   {"type": "photo"|"video"|..., "file_id": "...",
    --    "message_id": <int|null>, ...}
    -- Array order IS the album ordering contract.
    -- -----------------------------------------------------

    items JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(items) = 'array'),

    raw_caption TEXT NOT NULL DEFAULT '',

    caption_entities JSONB,

    forward_source JSONB,

    blockquote_blocks JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(blockquote_blocks) = 'array'),

    expandable_blocks JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(expandable_blocks) = 'array'),

    other_entities JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(other_entities) = 'array'),

    -- -----------------------------------------------------
    -- GENERATIONS
    -- -----------------------------------------------------

    generation INTEGER NOT NULL DEFAULT 0
        CHECK (generation >= 0),

    published_generation INTEGER
        CHECK (published_generation IS NULL OR published_generation >= 0),

    timer_generation INTEGER NOT NULL DEFAULT 0
        CHECK (timer_generation >= 0),

    leased_generation INTEGER
        CHECK (leased_generation IS NULL OR leased_generation >= 0),

    delivery_generation INTEGER NOT NULL DEFAULT 1
        CHECK (delivery_generation >= 1),

    -- -----------------------------------------------------
    -- EDITORIAL ALBUM STATE (fields that live on the
    -- in-memory media-group object today)
    -- -----------------------------------------------------

    editorial_finalized BOOLEAN NOT NULL DEFAULT FALSE,

    editorial_approved_text TEXT,

    editorial_retry_items JSONB
        CHECK (
            editorial_retry_items IS NULL
            OR jsonb_typeof(editorial_retry_items) = 'array'
        ),

    -- -----------------------------------------------------
    -- RETRY / RECOVERY
    -- -----------------------------------------------------

    recovery_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),

    last_error TEXT,

    -- -----------------------------------------------------
    -- PROCESSING LEASE (cross-worker is_processing)
    -- -----------------------------------------------------

    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,

    -- -----------------------------------------------------
    -- TIMESTAMPS (recovery + cleanup)
    -- -----------------------------------------------------

    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT media_group_state_unique
        UNIQUE (chat_id, media_group_id)
);


-- =========================================================
-- INDEXES
-- =========================================================

-- Recovery / re-drive sweeps: rows stuck in non-terminal states
-- with an expired (or absent) lease.
CREATE INDEX IF NOT EXISTS
    media_group_state_state_lease_idx
ON public.media_group_state (
    state,
    lease_expires_at
);

-- TTL cleanup sweeps: oldest activity first.
CREATE INDEX IF NOT EXISTS
    media_group_state_last_activity_idx
ON public.media_group_state (
    last_activity_at
);


-- =========================================================
-- UPDATED_AT TRIGGER
-- =========================================================

CREATE OR REPLACE FUNCTION public.set_media_group_state_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS
    media_group_state_updated_at
ON public.media_group_state;

CREATE TRIGGER media_group_state_updated_at
BEFORE UPDATE
ON public.media_group_state
FOR EACH ROW
EXECUTE FUNCTION public.set_media_group_state_updated_at();


-- =========================================================
-- ATOMIC GENERATION CLAIM RPC
-- =========================================================
--
-- claim_media_group_generation:
--
-- - Safe across multiple workers: SELECT ... FOR UPDATE row lock
--   plus a lease (lease_owner / lease_expires_at) make the
--   processing claim atomic; a second worker cannot claim while a
--   live lease is held.
-- - Prevents two workers from publishing the same generation:
--   only one claimant can hold the lease for the current
--   delivery_generation.
-- - Stale-generation claims (p_delivery_generation not equal to
--   the row's current delivery_generation) are rejected so an old
--   generation can never process or republish over a newer one.
-- - Claiming NEVER marks a generation published: the RPC does not
--   touch published_generation and never writes state='published'.
-- - Recovery semantics: an expired lease is reclaimable; a group
--   already durably published for the current generation and a
--   failed_terminal group are never re-claimed; the attempt cap
--   (5, = MEDIA_GROUP_MAX_RETRIES) transitions to failed_terminal.
--
-- Follows the same service-role-only model as the persistent
-- publication state RPCs (019/020/021/reclaim).
-- =========================================================

CREATE OR REPLACE FUNCTION public.claim_media_group_generation(
    p_chat_id BIGINT,
    p_media_group_id TEXT,
    p_delivery_generation INTEGER DEFAULT NULL,
    p_lease_owner TEXT DEFAULT NULL,
    p_lease_seconds INTEGER DEFAULT 120
)
RETURNS TABLE (
    claimed BOOLEAN,
    media_group_state_id BIGINT,
    current_delivery_generation INTEGER,
    current_generation INTEGER,
    current_state TEXT,
    current_attempt_count INTEGER,
    current_lease_expires_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_id BIGINT;
    v_state TEXT;
    v_generation INTEGER;
    v_published_generation INTEGER;
    v_delivery_generation INTEGER;
    v_attempt_count INTEGER;
    v_lease_expires_at TIMESTAMPTZ;
    v_has_active_lease BOOLEAN;
    v_now TIMESTAMPTZ := NOW();
    v_lease_seconds INTEGER := GREATEST(
        30,
        LEAST(
            COALESCE(p_lease_seconds, 120),
            900
        )
    );
BEGIN
    IF p_chat_id IS NULL THEN
        RAISE EXCEPTION 'chat_id is required';
    END IF;

    IF NULLIF(BTRIM(COALESCE(p_media_group_id, '')), '') IS NULL THEN
        RAISE EXCEPTION 'media_group_id is required';
    END IF;

    IF (
        p_delivery_generation IS NOT NULL
        AND p_delivery_generation < 1
    ) THEN
        RAISE EXCEPTION 'delivery_generation must be positive';
    END IF;

    SELECT
        mgs.id,
        mgs.state,
        mgs.generation,
        mgs.published_generation,
        mgs.delivery_generation,
        mgs.attempt_count,
        mgs.lease_expires_at
    INTO
        v_id,
        v_state,
        v_generation,
        v_published_generation,
        v_delivery_generation,
        v_attempt_count,
        v_lease_expires_at
    FROM public.media_group_state AS mgs
    WHERE
        mgs.chat_id = p_chat_id
        AND mgs.media_group_id = p_media_group_id
    FOR UPDATE;

    IF v_id IS NULL THEN
        -- Unknown group. Creation is owned by the application layer
        -- (in-memory first, then dual-write), so this is a soft no.
        RETURN QUERY
        SELECT
            FALSE,
            NULL::BIGINT,
            NULL::INTEGER,
            NULL::INTEGER,
            NULL::TEXT,
            NULL::INTEGER,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    -- Stale-generation guard: a claimant for any generation other
    -- than the row's current delivery_generation must not process
    -- or republish over the live one.
    IF (
        p_delivery_generation IS NOT NULL
        AND p_delivery_generation <> v_delivery_generation
    ) THEN
        RETURN QUERY
        SELECT
            FALSE,
            v_id,
            v_delivery_generation,
            v_generation,
            v_state,
            v_attempt_count,
            v_lease_expires_at;
        RETURN;
    END IF;

    -- Durable published guard: this generation is already published.
    -- Claiming must never mark a generation published, and must
    -- never republish one that is durably published.
    IF (
        v_state = 'published'
        AND v_published_generation IS NOT NULL
        AND v_published_generation >= v_delivery_generation
    ) THEN
        RETURN QUERY
        SELECT
            FALSE,
            v_id,
            v_delivery_generation,
            v_generation,
            v_state,
            v_attempt_count,
            v_lease_expires_at;
        RETURN;
    END IF;

    IF v_state = 'failed_terminal' THEN
        RETURN QUERY
        SELECT
            FALSE,
            v_id,
            v_delivery_generation,
            v_generation,
            v_state,
            v_attempt_count,
            v_lease_expires_at;
        RETURN;
    END IF;

    -- Active lease held by another worker (the cross-worker
    -- equivalent of is_processing). An expired lease is reclaimable:
    -- this preserves crash/deploy recovery semantics.
    v_has_active_lease := (
        v_lease_expires_at IS NOT NULL
        AND v_lease_expires_at > v_now
    );

    IF v_has_active_lease THEN
        RETURN QUERY
        SELECT
            FALSE,
            v_id,
            v_delivery_generation,
            v_generation,
            v_state,
            v_attempt_count,
            v_lease_expires_at;
        RETURN;
    END IF;

    -- Retry cap mirrors MEDIA_GROUP_MAX_RETRIES = 5. The application
    -- layer resets attempt_count when it starts a new
    -- delivery_generation.
    IF COALESCE(v_attempt_count, 0) >= 5 THEN
        UPDATE public.media_group_state AS mgs
        SET
            state = 'failed_terminal',
            last_error = 'media group attempt limit reached',
            lease_owner = NULL,
            lease_expires_at = NULL
        WHERE mgs.id = v_id;

        RETURN QUERY
        SELECT
            FALSE,
            v_id,
            v_delivery_generation,
            v_generation,
            'failed_terminal'::TEXT,
            v_attempt_count,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    -- Take the processing lease. Content generations, ordering,
    -- published_generation and lifecycle progress states are NOT
    -- touched here; the application advances them exactly as the
    -- in-memory state machine does today.
    UPDATE public.media_group_state AS mgs
    SET
        state = 'leased',
        attempt_count = mgs.attempt_count + 1,
        last_error = NULL,
        lease_owner = NULLIF(
            BTRIM(COALESCE(p_lease_owner, '')),
            ''
        ),
        lease_expires_at =
            v_now
            + make_interval(
                secs => v_lease_seconds
            )
    WHERE mgs.id = v_id
    RETURNING
        mgs.attempt_count,
        mgs.lease_expires_at
    INTO
        v_attempt_count,
        v_lease_expires_at;

    RETURN QUERY
    SELECT
        TRUE,
        v_id,
        v_delivery_generation,
        v_generation,
        'leased'::TEXT,
        v_attempt_count,
        v_lease_expires_at;
END;
$$;


-- =========================================================
-- SECURITY
-- =========================================================

ALTER TABLE public.media_group_state
ENABLE ROW LEVEL SECURITY;


REVOKE ALL
ON TABLE public.media_group_state
FROM PUBLIC, anon, authenticated;


REVOKE ALL
ON SEQUENCE public.media_group_state_id_seq
FROM PUBLIC, anon, authenticated;


GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.media_group_state
TO service_role;


GRANT USAGE, SELECT
ON SEQUENCE public.media_group_state_id_seq
TO service_role;


REVOKE ALL
ON FUNCTION public.claim_media_group_generation(
    BIGINT,
    TEXT,
    INTEGER,
    TEXT,
    INTEGER
)
FROM PUBLIC, anon, authenticated;


GRANT EXECUTE
ON FUNCTION public.claim_media_group_generation(
    BIGINT,
    TEXT,
    INTEGER,
    TEXT,
    INTEGER
)
TO service_role;


-- Trigger function must not be callable by client roles.
REVOKE ALL
ON FUNCTION public.set_media_group_state_updated_at()
FROM PUBLIC, anon, authenticated;


GRANT EXECUTE
ON FUNCTION public.set_media_group_state_updated_at()
TO service_role;


NOTIFY pgrst, 'reload schema';

COMMIT;
