BEGIN;

-- =========================================================
-- ATOMIC PUBLICATION DESTINATION CLAIM
-- =========================================================
-- Prevent two workers from publishing the same logical
-- destination at the same time.
--
-- Runtime access:
--   service_role only
-- =========================================================


CREATE OR REPLACE FUNCTION public.claim_publication_delivery(
    p_source_key TEXT,
    p_canonical_identity TEXT,
    p_platform TEXT,
    p_destination_chat_id TEXT DEFAULT '',
    p_workspace_id BIGINT DEFAULT NULL,
    p_destination_id BIGINT DEFAULT NULL,
    p_delivery_generation INTEGER DEFAULT 1,
    p_lease_owner TEXT DEFAULT NULL,
    p_lease_seconds INTEGER DEFAULT 120
)
RETURNS TABLE (
    claimed BOOLEAN,
    source_id BIGINT,
    delivery_id BIGINT,
    status TEXT,
    attempt_count INTEGER,
    lease_expires_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_source_id BIGINT;
    v_delivery_id BIGINT;
    v_status TEXT;
    v_attempt_count INTEGER;
    v_lease_expires_at TIMESTAMPTZ;
    v_now TIMESTAMPTZ := NOW();
    v_lease_seconds INTEGER := GREATEST(
        30,
        LEAST(
            COALESCE(p_lease_seconds, 120),
            900
        )
    );
BEGIN
    IF NULLIF(BTRIM(p_source_key), '') IS NULL THEN
        RAISE EXCEPTION
            'source_key is required';
    END IF;

    IF NULLIF(
        BTRIM(p_canonical_identity),
        ''
    ) IS NULL THEN
        RAISE EXCEPTION
            'canonical_identity is required';
    END IF;

    IF COALESCE(p_delivery_generation, 0) < 1 THEN
        RAISE EXCEPTION
            'delivery_generation must be positive';
    END IF;


    -- -----------------------------------------------------
    -- Logical source
    -- -----------------------------------------------------

    INSERT INTO public.publication_sources (
        source_key,
        delivery_generation,
        status
    )
    VALUES (
        p_source_key,
        p_delivery_generation,
        'pending'
    )
    ON CONFLICT (source_key)
    DO NOTHING;

    SELECT ps.id
    INTO v_source_id
    FROM public.publication_sources ps
    WHERE ps.source_key = p_source_key
    FOR UPDATE;


    -- -----------------------------------------------------
    -- Physical destination
    -- -----------------------------------------------------

    INSERT INTO public.publication_deliveries (
        source_id,
        workspace_id,
        destination_id,
        platform,
        destination_chat_id,
        canonical_identity,
        delivery_generation,
        status
    )
    VALUES (
        v_source_id,
        p_workspace_id,
        p_destination_id,
        COALESCE(p_platform, ''),
        COALESCE(
            p_destination_chat_id,
            ''
        ),
        p_canonical_identity,
        p_delivery_generation,
        'pending'
    )
    ON CONFLICT (
        source_id,
        canonical_identity,
        delivery_generation
    )
    DO NOTHING;


    SELECT
        pd.id,
        pd.status,
        pd.attempt_count,
        pd.lease_expires_at
    INTO
        v_delivery_id,
        v_status,
        v_attempt_count,
        v_lease_expires_at
    FROM public.publication_deliveries pd
    WHERE
        pd.source_id = v_source_id
        AND pd.canonical_identity =
            p_canonical_identity
        AND pd.delivery_generation =
            p_delivery_generation
    FOR UPDATE;


    -- -----------------------------------------------------
    -- Already succeeded
    -- -----------------------------------------------------

    IF v_status = 'succeeded' THEN
        RETURN QUERY
        SELECT
            FALSE,
            v_source_id,
            v_delivery_id,
            v_status,
            v_attempt_count,
            v_lease_expires_at;

        RETURN;
    END IF;


    -- -----------------------------------------------------
    -- Terminal failure
    -- -----------------------------------------------------

    IF v_status = 'failed_terminal' THEN
        RETURN QUERY
        SELECT
            FALSE,
            v_source_id,
            v_delivery_id,
            v_status,
            v_attempt_count,
            v_lease_expires_at;

        RETURN;
    END IF;


    -- -----------------------------------------------------
    -- Active lease held by another execution
    -- -----------------------------------------------------

    IF
        v_status = 'sending'
        AND v_lease_expires_at IS NOT NULL
        AND v_lease_expires_at > v_now
    THEN
        RETURN QUERY
        SELECT
            FALSE,
            v_source_id,
            v_delivery_id,
            v_status,
            v_attempt_count,
            v_lease_expires_at;

        RETURN;
    END IF;


    -- -----------------------------------------------------
    -- Maximum attempts
    -- -----------------------------------------------------

    IF COALESCE(v_attempt_count, 0) >= 5 THEN
        UPDATE public.publication_deliveries
        SET
            status = 'failed_terminal',
            lease_owner = NULL,
            lease_expires_at = NULL
        WHERE id = v_delivery_id;

        RETURN QUERY
        SELECT
            FALSE,
            v_source_id,
            v_delivery_id,
            'failed_terminal'::TEXT,
            v_attempt_count,
            NULL::TIMESTAMPTZ;

        RETURN;
    END IF;


    -- -----------------------------------------------------
    -- Acquire lease atomically
    -- -----------------------------------------------------

    UPDATE public.publication_deliveries
    SET
        status = 'sending',
        attempt_count =
            attempt_count + 1,
        last_error = NULL,
        lease_owner = NULLIF(
            BTRIM(
                COALESCE(
                    p_lease_owner,
                    ''
                )
            ),
            ''
        ),
        lease_expires_at =
            v_now
            + make_interval(
                secs => v_lease_seconds
            )
    WHERE id = v_delivery_id
    RETURNING
        attempt_count,
        lease_expires_at
    INTO
        v_attempt_count,
        v_lease_expires_at;


    UPDATE public.publication_sources
    SET
        status = 'sending',
        attempt_count =
            attempt_count + 1,
        last_error = NULL,
        lease_owner = NULLIF(
            BTRIM(
                COALESCE(
                    p_lease_owner,
                    ''
                )
            ),
            ''
        ),
        lease_expires_at =
            v_lease_expires_at
    WHERE id = v_source_id;


    RETURN QUERY
    SELECT
        TRUE,
        v_source_id,
        v_delivery_id,
        'sending'::TEXT,
        v_attempt_count,
        v_lease_expires_at;
END;
$$;


-- =========================================================
-- SECURITY
-- =========================================================

REVOKE ALL
ON FUNCTION public.claim_publication_delivery(
    TEXT,
    TEXT,
    TEXT,
    TEXT,
    BIGINT,
    BIGINT,
    INTEGER,
    TEXT,
    INTEGER
)
FROM PUBLIC, anon, authenticated;

GRANT EXECUTE
ON FUNCTION public.claim_publication_delivery(
    TEXT,
    TEXT,
    TEXT,
    TEXT,
    BIGINT,
    BIGINT,
    INTEGER,
    TEXT,
    INTEGER
)
TO service_role;


NOTIFY pgrst, 'reload schema';

COMMIT;
