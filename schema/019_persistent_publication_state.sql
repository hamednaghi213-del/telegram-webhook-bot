BEGIN;

-- =========================================================
-- PERSISTENT PUBLICATION STATE
-- =========================================================
-- Durable idempotency for Shared Publication Engine.
--
-- Goals:
--   1. One logical source survives restart/redeploy.
--   2. One physical destination is never published twice
--      after it has succeeded.
--   3. Delivery parts are persisted independently so retry
--      can resume without repeating successful parts.
--   4. Runtime access is service_role only.
-- =========================================================


-- =========================================================
-- PUBLICATION SOURCES
-- =========================================================

CREATE TABLE IF NOT EXISTS public.publication_sources (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_key TEXT NOT NULL UNIQUE,

    actor_user_id BIGINT
        REFERENCES public.users(id)
        ON DELETE SET NULL,

    source_kind TEXT NOT NULL DEFAULT 'message',

    delivery_generation INTEGER NOT NULL DEFAULT 1
        CHECK (delivery_generation > 0),

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'sending',
                'partial',
                'succeeded',
                'failed',
                'failed_terminal'
            )
        ),

    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),

    last_error TEXT,

    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- =========================================================
-- PUBLICATION DELIVERIES
-- =========================================================

CREATE TABLE IF NOT EXISTS public.publication_deliveries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_id BIGINT NOT NULL
        REFERENCES public.publication_sources(id)
        ON DELETE CASCADE,

    workspace_id BIGINT
        REFERENCES public.workspaces(id)
        ON DELETE SET NULL,

    destination_id BIGINT
        REFERENCES public.publication_destinations(id)
        ON DELETE SET NULL,

    platform TEXT NOT NULL,

    destination_chat_id TEXT NOT NULL DEFAULT '',

    canonical_identity TEXT NOT NULL,

    delivery_generation INTEGER NOT NULL DEFAULT 1
        CHECK (delivery_generation > 0),

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'sending',
                'succeeded',
                'failed',
                'failed_terminal'
            )
        ),

    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),

    last_error TEXT,

    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT publication_deliveries_source_identity_unique
        UNIQUE (
            source_id,
            canonical_identity,
            delivery_generation
        )
);


-- =========================================================
-- PUBLICATION DELIVERY PARTS
-- =========================================================

CREATE TABLE IF NOT EXISTS public.publication_delivery_parts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    delivery_id BIGINT NOT NULL
        REFERENCES public.publication_deliveries(id)
        ON DELETE CASCADE,

    part_key TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'sending',
                'succeeded',
                'failed',
                'failed_terminal'
            )
        ),

    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),

    message_id BIGINT,

    message_ids JSONB,

    destination_chat_id TEXT,

    last_error TEXT,

    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT publication_delivery_parts_unique
        UNIQUE (
            delivery_id,
            part_key
        )
);


-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX IF NOT EXISTS
    publication_sources_status_lease_idx
ON public.publication_sources (
    status,
    lease_expires_at
);

CREATE INDEX IF NOT EXISTS
    publication_deliveries_source_idx
ON public.publication_deliveries (
    source_id
);

CREATE INDEX IF NOT EXISTS
    publication_deliveries_status_lease_idx
ON public.publication_deliveries (
    status,
    lease_expires_at
);

CREATE INDEX IF NOT EXISTS
    publication_parts_delivery_idx
ON public.publication_delivery_parts (
    delivery_id
);

CREATE INDEX IF NOT EXISTS
    publication_parts_status_lease_idx
ON public.publication_delivery_parts (
    status,
    lease_expires_at
);


-- =========================================================
-- UPDATED_AT TRIGGER
-- =========================================================

CREATE OR REPLACE FUNCTION public.set_publication_state_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS
    publication_sources_updated_at
ON public.publication_sources;

CREATE TRIGGER publication_sources_updated_at
BEFORE UPDATE
ON public.publication_sources
FOR EACH ROW
EXECUTE FUNCTION public.set_publication_state_updated_at();


DROP TRIGGER IF EXISTS
    publication_deliveries_updated_at
ON public.publication_deliveries;

CREATE TRIGGER publication_deliveries_updated_at
BEFORE UPDATE
ON public.publication_deliveries
FOR EACH ROW
EXECUTE FUNCTION public.set_publication_state_updated_at();


DROP TRIGGER IF EXISTS
    publication_delivery_parts_updated_at
ON public.publication_delivery_parts;

CREATE TRIGGER publication_delivery_parts_updated_at
BEFORE UPDATE
ON public.publication_delivery_parts
FOR EACH ROW
EXECUTE FUNCTION public.set_publication_state_updated_at();


-- =========================================================
-- SECURITY
-- =========================================================

ALTER TABLE public.publication_sources
ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.publication_deliveries
ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.publication_delivery_parts
ENABLE ROW LEVEL SECURITY;


REVOKE ALL
ON TABLE public.publication_sources
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON TABLE public.publication_deliveries
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON TABLE public.publication_delivery_parts
FROM PUBLIC, anon, authenticated;


REVOKE ALL
ON SEQUENCE public.publication_sources_id_seq
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON SEQUENCE public.publication_deliveries_id_seq
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON SEQUENCE public.publication_delivery_parts_id_seq
FROM PUBLIC, anon, authenticated;


GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.publication_sources
TO service_role;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.publication_deliveries
TO service_role;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.publication_delivery_parts
TO service_role;


GRANT USAGE, SELECT
ON SEQUENCE public.publication_sources_id_seq
TO service_role;

GRANT USAGE, SELECT
ON SEQUENCE public.publication_deliveries_id_seq
TO service_role;

GRANT USAGE, SELECT
ON SEQUENCE public.publication_delivery_parts_id_seq
TO service_role;


-- Trigger function must not be callable by client roles.
REVOKE ALL
ON FUNCTION public.set_publication_state_updated_at()
FROM PUBLIC, anon, authenticated;

GRANT EXECUTE
ON FUNCTION public.set_publication_state_updated_at()
TO service_role;


NOTIFY pgrst, 'reload schema';

COMMIT;
