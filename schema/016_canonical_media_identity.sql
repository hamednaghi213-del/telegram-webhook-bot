BEGIN;

CREATE TABLE IF NOT EXISTS public.media_identities (
    id BIGSERIAL PRIMARY KEY,
    identity_key TEXT NULL UNIQUE,
    media_name TEXT NOT NULL,
    hashtag TEXT NOT NULL DEFAULT '',
    channel_tag TEXT NOT NULL DEFAULT '',
    publication_icons JSONB NOT NULL DEFAULT '[]'::jsonb,
    icons_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    publication_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    CHECK (btrim(media_name) <> ''),
    CHECK (identity_key IS NULL OR btrim(identity_key) <> ''),
    CHECK (jsonb_typeof(publication_icons) = 'array'),
    CHECK (jsonb_typeof(publication_profile) = 'object')
);

CREATE TABLE IF NOT EXISTS public.media_identity_members (
    media_identity_id BIGINT NOT NULL
        REFERENCES public.media_identities(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL
        REFERENCES public.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL
        CHECK (role IN ('owner', 'manager', 'publisher', 'writer')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'removed')),
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    PRIMARY KEY (media_identity_id, user_id)
);

ALTER TABLE public.publication_destinations
    ADD COLUMN IF NOT EXISTS media_identity_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS normalized_external_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS platform_chat_id TEXT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'publication_destinations_media_identity_id_fkey'
          AND conrelid = 'public.publication_destinations'::regclass
    ) THEN
        ALTER TABLE public.publication_destinations
            ADD CONSTRAINT publication_destinations_media_identity_id_fkey
            FOREIGN KEY (media_identity_id)
            REFERENCES public.media_identities(id)
            ON DELETE RESTRICT;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS public.workspace_destinations (
    workspace_id BIGINT NOT NULL
        REFERENCES public.workspaces(id) ON DELETE CASCADE,
    destination_id BIGINT NOT NULL
        REFERENCES public.publication_destinations(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'removed')),
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    PRIMARY KEY (workspace_id, destination_id)
);

-- Current product semantics place one physical destination in one group at a
-- time.  The association table keeps that policy separate from destination
-- identity and can later be relaxed without moving identity/branding data.
CREATE UNIQUE INDEX IF NOT EXISTS workspace_destinations_one_active_group
    ON public.workspace_destinations (destination_id)
    WHERE status = 'active';

CREATE UNIQUE INDEX IF NOT EXISTS publication_destinations_canonical_identity_unique
    ON public.publication_destinations (platform, normalized_external_id)
    WHERE normalized_external_id IS NOT NULL AND status <> 'removed';

CREATE INDEX IF NOT EXISTS publication_destinations_media_identity_idx
    ON public.publication_destinations (media_identity_id);
CREATE INDEX IF NOT EXISTS workspace_destinations_workspace_status_idx
    ON public.workspace_destinations (workspace_id, status);
CREATE INDEX IF NOT EXISTS media_identity_members_user_status_idx
    ON public.media_identity_members (user_id, status);

ALTER TABLE public.destination_branding
    ADD COLUMN IF NOT EXISTS publication_profile JSONB NULL;

CREATE OR REPLACE FUNCTION public.move_workspace_destination_memberships(
    p_destination_ids BIGINT[],
    p_target_workspace_id BIGINT
)
RETURNS SETOF public.workspace_destinations
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    PERFORM 1
    FROM public.publication_destinations
    WHERE id = ANY (p_destination_ids)
    ORDER BY id
    FOR UPDATE;

    IF (SELECT count(*) FROM public.publication_destinations
        WHERE id = ANY (p_destination_ids)) <> cardinality(p_destination_ids) THEN
        RAISE EXCEPTION 'unknown canonical destination';
    END IF;

    UPDATE public.workspace_destinations
    SET status = 'removed', updated_at = EXTRACT(EPOCH FROM NOW())
    WHERE destination_id = ANY (p_destination_ids)
      AND status = 'active';

    INSERT INTO public.workspace_destinations (
        workspace_id, destination_id, status, updated_at
    )
    SELECT p_target_workspace_id, destination_id, 'active', EXTRACT(EPOCH FROM NOW())
    FROM unnest(p_destination_ids) AS destination_id
    ON CONFLICT (workspace_id, destination_id)
    DO UPDATE SET status = 'active', updated_at = EXCLUDED.updated_at;

    RETURN QUERY
    SELECT wd.*
    FROM public.workspace_destinations wd
    WHERE wd.workspace_id = p_target_workspace_id
      AND wd.destination_id = ANY (p_destination_ids)
      AND wd.status = 'active'
    ORDER BY wd.destination_id;
END;
$$;

REVOKE ALL ON FUNCTION public.move_workspace_destination_memberships(BIGINT[], BIGINT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.move_workspace_destination_memberships(BIGINT[], BIGINT)
    TO service_role;

CREATE OR REPLACE FUNCTION public.claim_legacy_destination_canonical(
    p_user_id BIGINT,
    p_workspace_id BIGINT,
    p_identity_key TEXT,
    p_platform TEXT,
    p_external_id TEXT,
    p_media_name TEXT,
    p_hashtag TEXT DEFAULT '',
    p_channel_tag TEXT DEFAULT ''
)
RETURNS public.publication_destinations
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    v_normalized TEXT := lower(ltrim(btrim(p_external_id), '@'));
    v_media_id BIGINT;
    v_destination public.publication_destinations;
    v_existing BOOLEAN := FALSE;
BEGIN
    IF p_platform NOT IN ('telegram', 'bale') OR v_normalized = '' THEN
        RAISE EXCEPTION 'invalid canonical destination identity';
    END IF;

    SELECT * INTO v_destination
    FROM public.publication_destinations
    WHERE platform = p_platform
      AND normalized_external_id = v_normalized
      AND status <> 'removed'
    FOR UPDATE;

    IF FOUND THEN
        v_existing := TRUE;
        v_media_id := v_destination.media_identity_id;
        IF v_media_id IS NULL THEN
            RAISE EXCEPTION 'existing destination requires reviewed media identity mapping';
        END IF;
    ELSE
        SELECT id INTO v_media_id
        FROM public.media_identities
        WHERE identity_key = btrim(p_identity_key)
        FOR UPDATE;

        IF NOT FOUND THEN
            INSERT INTO public.media_identities (
                identity_key, media_name, hashtag, channel_tag
            ) VALUES (
                btrim(p_identity_key), btrim(p_media_name),
                btrim(p_hashtag), btrim(p_channel_tag)
            ) RETURNING id INTO v_media_id;
        ELSE
            v_existing := TRUE;
        END IF;

        INSERT INTO public.publication_destinations (
            workspace_id, media_identity_id, platform, destination_type,
            name, external_id, normalized_external_id, status, is_default
        ) VALUES (
            p_workspace_id, v_media_id, p_platform, 'channel',
            p_external_id, p_external_id, v_normalized, 'active', FALSE
        ) RETURNING * INTO v_destination;
    END IF;

    IF v_existing AND NOT EXISTS (
        SELECT 1 FROM public.media_identity_members
        WHERE media_identity_id = v_media_id
          AND user_id = p_user_id
          AND status = 'active'
    ) THEN
        RAISE EXCEPTION 'explicit verified media access grant required';
    END IF;

    IF NOT v_existing THEN
        INSERT INTO public.media_identity_members (
            media_identity_id, user_id, role, status
        ) VALUES (v_media_id, p_user_id, 'owner', 'active');
    END IF;

    INSERT INTO public.destination_verification (
        destination_id, verified, verification_note, updated_at
    ) VALUES (
        v_destination.id, TRUE, 'verified Legacy canonical claim',
        EXTRACT(EPOCH FROM NOW())
    )
    ON CONFLICT (destination_id)
    DO UPDATE SET
        verified = TRUE,
        verification_note = EXCLUDED.verification_note,
        updated_at = EXCLUDED.updated_at;

    PERFORM public.move_workspace_destination_memberships(
        ARRAY[v_destination.id], p_workspace_id
    );

    RETURN v_destination;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_legacy_destination_canonical(
    BIGINT, BIGINT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_legacy_destination_canonical(
    BIGINT, BIGINT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT
) TO service_role;

REVOKE ALL ON TABLE public.media_identities,
    public.media_identity_members,
    public.workspace_destinations
    FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.media_identities,
    public.media_identity_members,
    public.workspace_destinations
    TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.media_identities_id_seq TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;
