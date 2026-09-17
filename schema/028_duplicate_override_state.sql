-- =========================================================
-- 028 — B8: PERSISTENT DUPLICATE OVERRIDE TOKENS
-- =========================================================
--
-- Durable, single-use, cross-worker-safe storage for Duplicate News
-- Guard override tokens ("publish anyway" buttons).
--
-- DESIGN:
--
-- - Only a reconstructable descriptor is persisted. The in-memory
--   PreparedContent object is NOT persisted; the application
--   re-prepares content from the descriptor when the override is
--   consumed.
-- - A token is consumed atomically: the consume RPC deletes the
--   row and returns it in the same statement, so two workers can
--   never both consume the same token.
-- - Rows expire (expires_at) and are cleaned up lazily.
--
-- The migration is additive and rollback-safe: no existing table,
-- RPC or view is altered or dropped.
-- =========================================================

BEGIN;

-- =========================================================
-- TABLE
-- =========================================================

CREATE TABLE IF NOT EXISTS public.duplicate_override_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    token TEXT NOT NULL,

    chat_id BIGINT NOT NULL,

    -- Re-preparable descriptor (no opaque PreparedContent):
    -- content fields needed by the application to re-run content
    -- preparation and target resolution on consume.
    descriptor JSONB NOT NULL
        CHECK (jsonb_typeof(descriptor) = 'object'),

    expires_at TIMESTAMPTZ NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT duplicate_override_tokens_unique
        UNIQUE (token)
);


-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX IF NOT EXISTS
    duplicate_override_tokens_expires_idx
ON public.duplicate_override_tokens (
    expires_at
);


-- =========================================================
-- ATOMIC CONSUME RPC
-- =========================================================
--
-- consume_duplicate_override:
--
-- - Atomic single-use consume: DELETE ... RETURNING under the
--   default row lock means exactly one caller ever receives the
--   token payload; a second caller gets claimed=false.
-- - Ownership is enforced server-side: the row is only returned
--   when p_chat_id matches the stored chat_id.
-- - Expired tokens are treated as absent.
-- =========================================================

CREATE OR REPLACE FUNCTION public.consume_duplicate_override(
    p_token TEXT,
    p_chat_id BIGINT
)
RETURNS TABLE (
    consumed BOOLEAN,
    descriptor JSONB
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_descriptor JSONB;
BEGIN
    IF NULLIF(BTRIM(COALESCE(p_token, '')), '') IS NULL THEN
        RAISE EXCEPTION 'token is required';
    END IF;

    IF p_chat_id IS NULL THEN
        RAISE EXCEPTION 'chat_id is required';
    END IF;

    DELETE FROM public.duplicate_override_tokens AS dot
    WHERE
        dot.token = p_token
        AND dot.chat_id = p_chat_id
        AND dot.expires_at > NOW()
    RETURNING dot.descriptor
    INTO v_descriptor;

    IF v_descriptor IS NULL THEN
        RETURN QUERY
        SELECT
            FALSE,
            NULL::JSONB;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        TRUE,
        v_descriptor;
END;
$$;


-- =========================================================
-- SECURITY
-- =========================================================

ALTER TABLE public.duplicate_override_tokens
ENABLE ROW LEVEL SECURITY;


REVOKE ALL
ON TABLE public.duplicate_override_tokens
FROM PUBLIC, anon, authenticated;


REVOKE ALL
ON SEQUENCE public.duplicate_override_tokens_id_seq
FROM PUBLIC, anon, authenticated;


GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.duplicate_override_tokens
TO service_role;


GRANT USAGE, SELECT
ON SEQUENCE public.duplicate_override_tokens_id_seq
TO service_role;


REVOKE ALL
ON FUNCTION public.consume_duplicate_override(
    TEXT,
    BIGINT
)
FROM PUBLIC, anon, authenticated;


GRANT EXECUTE
ON FUNCTION public.consume_duplicate_override(
    TEXT,
    BIGINT
)
TO service_role;


NOTIFY pgrst, 'reload schema';

COMMIT;
