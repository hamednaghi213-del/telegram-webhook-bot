BEGIN;

-- =========================================================
-- 038_x_destination_foundation.sql
--
-- Foundation for X (Twitter) as a Workspace destination.
--
-- Goals:
--   1. Allow publication_destinations.platform = 'x'
--   2. Keep X account connection persistent per destination
--   3. Store OAuth credentials only as application-encrypted ciphertext
--   4. Support automatic token refresh / reconnect state
--   5. Support one-click OAuth reconnect with short-lived PKCE sessions
--
-- IMPORTANT:
--   Raw OAuth access/refresh tokens must NEVER be stored in these tables.
--   Encryption/decryption is handled by the application layer.
-- =========================================================


-- =========================================================
-- PUBLICATION DESTINATION PLATFORM
-- =========================================================

ALTER TABLE public.publication_destinations
    DROP CONSTRAINT IF EXISTS publication_destinations_platform_check;

ALTER TABLE public.publication_destinations
    ADD CONSTRAINT publication_destinations_platform_check
    CHECK (
        platform IN (
            'telegram',
            'bale',
            'x'
        )
    );


-- =========================================================
-- X OAUTH CONNECTION
-- =========================================================
-- One persistent X account connection per X destination.
--
-- connection_status:
--   connected
--       OAuth is usable.
--
--   reconnect_required
--       Refresh/authentication failed and the user must press
--       "🔄 اتصال مجدد X".
--
--   disconnected
--       User intentionally disconnected X.
-- =========================================================

CREATE TABLE IF NOT EXISTS public.x_oauth_connections (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    destination_id BIGINT NOT NULL
        REFERENCES public.publication_destinations(id)
        ON DELETE CASCADE,

    workspace_id BIGINT NOT NULL
        REFERENCES public.workspaces(id)
        ON DELETE CASCADE,

    connected_by_user_id BIGINT
        REFERENCES public.users(id)
        ON DELETE SET NULL,

    x_user_id TEXT,
    x_username TEXT,
    x_display_name TEXT,

    access_token_ciphertext TEXT,
    refresh_token_ciphertext TEXT,

    token_expires_at DOUBLE PRECISION,

    granted_scopes TEXT[] NOT NULL
        DEFAULT ARRAY[]::TEXT[],

    connection_status TEXT NOT NULL
        DEFAULT 'disconnected'
        CHECK (
            connection_status IN (
                'connected',
                'reconnect_required',
                'disconnected'
            )
        ),

    last_refresh_at DOUBLE PRECISION,
    last_connected_at DOUBLE PRECISION
        NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),

    last_error TEXT,

    created_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),

    updated_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),

    CONSTRAINT x_oauth_connections_destination_unique
        UNIQUE (destination_id)
);


CREATE INDEX IF NOT EXISTS
    x_oauth_connections_workspace_idx
ON public.x_oauth_connections (
    workspace_id
);


CREATE INDEX IF NOT EXISTS
    x_oauth_connections_status_idx
ON public.x_oauth_connections (
    connection_status
);


CREATE UNIQUE INDEX IF NOT EXISTS
    x_oauth_connections_workspace_x_user_unique
ON public.x_oauth_connections (
    workspace_id,
    x_user_id
)
WHERE
    x_user_id IS NOT NULL
    AND connection_status <> 'disconnected';


-- =========================================================
-- X OAUTH / PKCE SESSION
-- =========================================================
-- Short-lived state used during Connect / Reconnect.
--
-- We store only:
--   - hash of OAuth state
--   - encrypted PKCE verifier
--
-- Never persist the raw OAuth state or raw PKCE verifier.
-- =========================================================

CREATE TABLE IF NOT EXISTS public.x_oauth_sessions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    state_hash TEXT NOT NULL UNIQUE,

    workspace_id BIGINT NOT NULL
        REFERENCES public.workspaces(id)
        ON DELETE CASCADE,

    destination_id BIGINT
        REFERENCES public.publication_destinations(id)
        ON DELETE CASCADE,

    requested_by_user_id BIGINT
        REFERENCES public.users(id)
        ON DELETE SET NULL,

    action TEXT NOT NULL
        CHECK (
            action IN (
                'connect',
                'reconnect'
            )
        ),

    code_verifier_ciphertext TEXT NOT NULL,

    redirect_uri TEXT NOT NULL,

    expires_at DOUBLE PRECISION NOT NULL,

    consumed_at DOUBLE PRECISION,

    created_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),

    CHECK (
        btrim(state_hash) <> ''
    ),

    CHECK (
        btrim(code_verifier_ciphertext) <> ''
    ),

    CHECK (
        btrim(redirect_uri) <> ''
    )
);


CREATE INDEX IF NOT EXISTS
    x_oauth_sessions_workspace_idx
ON public.x_oauth_sessions (
    workspace_id
);


CREATE INDEX IF NOT EXISTS
    x_oauth_sessions_expiry_idx
ON public.x_oauth_sessions (
    expires_at,
    consumed_at
);


-- =========================================================
-- SERVICE ROLE ONLY
-- =========================================================
-- OAuth material must not be exposed to anon/authenticated
-- PostgREST clients.
-- =========================================================

ALTER TABLE public.x_oauth_connections
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.x_oauth_sessions
    ENABLE ROW LEVEL SECURITY;


REVOKE ALL
ON TABLE public.x_oauth_connections
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON TABLE public.x_oauth_sessions
FROM PUBLIC, anon, authenticated;


GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.x_oauth_connections
TO service_role;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.x_oauth_sessions
TO service_role;


GRANT USAGE, SELECT
ON SEQUENCE public.x_oauth_connections_id_seq
TO service_role;

GRANT USAGE, SELECT
ON SEQUENCE public.x_oauth_sessions_id_seq
TO service_role;


COMMIT;