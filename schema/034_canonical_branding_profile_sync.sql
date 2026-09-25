BEGIN;

-- =========================================================
-- 034 — CANONICAL BRANDING / ICONS / PROFILE SYNC
--
-- workspace_branding remains the existing setup/UI write model.
-- media_identities is the canonical publication identity.
--
-- This migration:
-- 1. Backfills existing workspace branding into media_identities.
-- 2. Ensures the workspace owner has canonical media ownership.
-- 3. Aligns active Telegram/Bale destinations with that media identity.
-- 4. Keeps future workspace_branding changes synchronized automatically.
-- =========================================================


-- =========================================================
-- SYNC FUNCTION
-- =========================================================

CREATE OR REPLACE FUNCTION public.sync_workspace_branding_to_media_identity()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_identity_key TEXT;
    v_media_id BIGINT;
    v_owner_user_id BIGINT;
    v_media_name TEXT;
BEGIN
    v_identity_key := 'workspace:' || NEW.workspace_id::TEXT;

    SELECT owner_user_id
    INTO v_owner_user_id
    FROM public.workspaces
    WHERE id = NEW.workspace_id;

    IF v_owner_user_id IS NULL THEN
        RAISE EXCEPTION
            'workspace % has no owner for canonical media sync',
            NEW.workspace_id;
    END IF;

    v_media_name := NULLIF(BTRIM(COALESCE(NEW.media_name, '')), '');

    IF v_media_name IS NULL THEN
        SELECT NULLIF(BTRIM(name), '')
        INTO v_media_name
        FROM public.workspaces
        WHERE id = NEW.workspace_id;
    END IF;

    IF v_media_name IS NULL THEN
        RAISE EXCEPTION
            'workspace % has no usable media name for canonical media sync',
            NEW.workspace_id;
    END IF;

    INSERT INTO public.media_identities (
        identity_key,
        media_name,
        hashtag,
        channel_tag,
        publication_icons,
        icons_enabled,
        publication_profile,
        status,
        updated_at
    )
    VALUES (
        v_identity_key,
        v_media_name,
        BTRIM(COALESCE(NEW.hashtag, '')),
        BTRIM(COALESCE(NEW.channel_tag, '')),
        COALESCE(NEW.publication_icons, '[]'::jsonb),
        COALESCE(NEW.icons_enabled, FALSE),
        COALESCE(NEW.publication_profile, '{}'::jsonb),
        'active',
        EXTRACT(EPOCH FROM NOW())
    )
    ON CONFLICT (identity_key)
    DO UPDATE SET
        media_name = EXCLUDED.media_name,
        hashtag = EXCLUDED.hashtag,
        channel_tag = EXCLUDED.channel_tag,
        publication_icons = EXCLUDED.publication_icons,
        icons_enabled = EXCLUDED.icons_enabled,
        publication_profile = EXCLUDED.publication_profile,
        updated_at = EXCLUDED.updated_at
    RETURNING id INTO v_media_id;

    INSERT INTO public.media_identity_members (
        media_identity_id,
        user_id,
        role,
        status,
        updated_at
    )
    VALUES (
        v_media_id,
        v_owner_user_id,
        'owner',
        'active',
        EXTRACT(EPOCH FROM NOW())
    )
    ON CONFLICT (media_identity_id, user_id)
    DO UPDATE SET
        role = 'owner',
        status = 'active',
        updated_at = EXCLUDED.updated_at;

    UPDATE public.publication_destinations AS pd
    SET
        media_identity_id = v_media_id,
        updated_at = EXTRACT(EPOCH FROM NOW())
    FROM public.workspace_destinations AS wd
    WHERE wd.workspace_id = NEW.workspace_id
      AND wd.destination_id = pd.id
      AND wd.status = 'active'
      AND pd.status <> 'removed'
      AND pd.media_identity_id IS DISTINCT FROM v_media_id;

    RETURN NEW;
END;
$$;


-- =========================================================
-- BACKFILL EXISTING WORKSPACE BRANDING
-- =========================================================

INSERT INTO public.media_identities (
    identity_key,
    media_name,
    hashtag,
    channel_tag,
    publication_icons,
    icons_enabled,
    publication_profile,
    status,
    updated_at
)
SELECT
    'workspace:' || wb.workspace_id::TEXT,
    COALESCE(
        NULLIF(BTRIM(wb.media_name), ''),
        NULLIF(BTRIM(w.name), '')
    ),
    BTRIM(COALESCE(wb.hashtag, '')),
    BTRIM(COALESCE(wb.channel_tag, '')),
    COALESCE(wb.publication_icons, '[]'::jsonb),
    COALESCE(wb.icons_enabled, FALSE),
    COALESCE(wb.publication_profile, '{}'::jsonb),
    'active',
    EXTRACT(EPOCH FROM NOW())
FROM public.workspace_branding AS wb
JOIN public.workspaces AS w
    ON w.id = wb.workspace_id
WHERE COALESCE(
    NULLIF(BTRIM(wb.media_name), ''),
    NULLIF(BTRIM(w.name), '')
) IS NOT NULL
ON CONFLICT (identity_key)
DO UPDATE SET
    media_name = EXCLUDED.media_name,
    hashtag = EXCLUDED.hashtag,
    channel_tag = EXCLUDED.channel_tag,
    publication_icons = EXCLUDED.publication_icons,
    icons_enabled = EXCLUDED.icons_enabled,
    publication_profile = EXCLUDED.publication_profile,
    updated_at = EXCLUDED.updated_at;


-- =========================================================
-- ENSURE OWNER MEMBERSHIP FOR BACKFILLED IDENTITIES
-- =========================================================

INSERT INTO public.media_identity_members (
    media_identity_id,
    user_id,
    role,
    status,
    updated_at
)
SELECT
    mi.id,
    w.owner_user_id,
    'owner',
    'active',
    EXTRACT(EPOCH FROM NOW())
FROM public.workspace_branding AS wb
JOIN public.workspaces AS w
    ON w.id = wb.workspace_id
JOIN public.media_identities AS mi
    ON mi.identity_key = 'workspace:' || wb.workspace_id::TEXT
WHERE w.owner_user_id IS NOT NULL
ON CONFLICT (media_identity_id, user_id)
DO UPDATE SET
    role = 'owner',
    status = 'active',
    updated_at = EXCLUDED.updated_at;


-- =========================================================
-- ALIGN EXISTING DESTINATIONS WITH CANONICAL MEDIA IDENTITY
-- =========================================================

UPDATE public.publication_destinations AS pd
SET
    media_identity_id = mi.id,
    updated_at = EXTRACT(EPOCH FROM NOW())
FROM public.workspace_destinations AS wd
JOIN public.media_identities AS mi
    ON mi.identity_key = 'workspace:' || wd.workspace_id::TEXT
WHERE wd.destination_id = pd.id
  AND wd.status = 'active'
  AND pd.status <> 'removed'
  AND pd.media_identity_id IS DISTINCT FROM mi.id;


-- =========================================================
-- FUTURE RUNTIME SYNC
-- =========================================================

DROP TRIGGER IF EXISTS workspace_branding_canonical_media_sync
ON public.workspace_branding;

CREATE TRIGGER workspace_branding_canonical_media_sync
AFTER INSERT OR UPDATE OF
    media_name,
    hashtag,
    channel_tag,
    publication_icons,
    icons_enabled,
    publication_profile
ON public.workspace_branding
FOR EACH ROW
EXECUTE FUNCTION public.sync_workspace_branding_to_media_identity();


-- Only database-internal trigger execution is intended.
REVOKE ALL ON FUNCTION public.sync_workspace_branding_to_media_identity()
FROM PUBLIC, anon, authenticated;

NOTIFY pgrst, 'reload schema';

COMMIT;
