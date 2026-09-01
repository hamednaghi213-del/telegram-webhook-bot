BEGIN;

CREATE OR REPLACE FUNCTION public.move_workspace_destination_memberships_authorized(
    p_user_id BIGINT,
    p_destination_ids BIGINT[],
    p_target_workspace_id BIGINT
)
RETURNS SETOF public.workspace_destinations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_destination_count INTEGER;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'user is required';
    END IF;

    IF p_target_workspace_id IS NULL THEN
        RAISE EXCEPTION 'target workspace is required';
    END IF;

    IF p_destination_ids IS NULL
       OR cardinality(p_destination_ids) = 0 THEN
        RAISE EXCEPTION 'at least one destination is required';
    END IF;

    -- Target workspace must be active and user must be owner/manager there.
    IF NOT EXISTS (
        SELECT 1
        FROM public.workspace_members wm
        JOIN public.workspaces w
          ON w.id = wm.workspace_id
        WHERE wm.workspace_id = p_target_workspace_id
          AND wm.user_id = p_user_id
          AND wm.status = 'active'
          AND wm.role IN ('owner', 'manager')
          AND w.status = 'active'
    ) THEN
        RAISE EXCEPTION 'target workspace access denied';
    END IF;

    -- Lock all requested physical destinations.
    PERFORM 1
    FROM public.publication_destinations pd
    WHERE pd.id = ANY (p_destination_ids)
      AND pd.status <> 'removed'
    ORDER BY pd.id
    FOR UPDATE;

    SELECT count(*)
    INTO v_destination_count
    FROM public.publication_destinations pd
    WHERE pd.id = ANY (p_destination_ids)
      AND pd.status <> 'removed';

    IF v_destination_count <> cardinality(p_destination_ids) THEN
        RAISE EXCEPTION 'unknown canonical destination';
    END IF;

    -- Every selected destination must currently belong to a workspace
    -- that the user is allowed to manage.
    IF EXISTS (
        SELECT 1
        FROM public.workspace_destinations wd
        WHERE wd.destination_id = ANY (p_destination_ids)
          AND wd.status = 'active'
          AND NOT EXISTS (
              SELECT 1
              FROM public.workspace_members wm
              JOIN public.workspaces w
                ON w.id = wm.workspace_id
              WHERE wm.workspace_id = wd.workspace_id
                AND wm.user_id = p_user_id
                AND wm.status = 'active'
                AND wm.role IN ('owner', 'manager')
                AND w.status = 'active'
          )
    ) THEN
        RAISE EXCEPTION 'source workspace access denied';
    END IF;

    -- Canonical media permission must also allow management.
    IF EXISTS (
        SELECT 1
        FROM public.publication_destinations pd
        WHERE pd.id = ANY (p_destination_ids)
          AND (
              pd.media_identity_id IS NULL
              OR NOT EXISTS (
                  SELECT 1
                  FROM public.media_identity_members mim
                  WHERE mim.media_identity_id = pd.media_identity_id
                    AND mim.user_id = p_user_id
                    AND mim.status = 'active'
                    AND mim.role IN ('owner', 'manager')
              )
          )
    ) THEN
        RAISE EXCEPTION 'media identity access denied';
    END IF;

    -- The destination must currently have an active association.
    IF EXISTS (
        SELECT 1
        FROM unnest(p_destination_ids) AS requested(destination_id)
        WHERE NOT EXISTS (
            SELECT 1
            FROM public.workspace_destinations wd
            WHERE wd.destination_id = requested.destination_id
              AND wd.status = 'active'
        )
    ) THEN
        RAISE EXCEPTION 'active workspace association missing';
    END IF;

    -- Prevent no-op move to the same target workspace.
    IF EXISTS (
        SELECT 1
        FROM public.workspace_destinations wd
        WHERE wd.destination_id = ANY (p_destination_ids)
          AND wd.workspace_id = p_target_workspace_id
          AND wd.status = 'active'
    ) THEN
        RAISE EXCEPTION 'destination already belongs to target workspace';
    END IF;

    UPDATE public.workspace_destinations
    SET
        status = 'removed',
        updated_at = EXTRACT(EPOCH FROM NOW())
    WHERE destination_id = ANY (p_destination_ids)
      AND status = 'active';

    INSERT INTO public.workspace_destinations (
        workspace_id,
        destination_id,
        status,
        created_at,
        updated_at
    )
    SELECT
        p_target_workspace_id,
        destination_id,
        'active',
        EXTRACT(EPOCH FROM NOW()),
        EXTRACT(EPOCH FROM NOW())
    FROM unnest(p_destination_ids) AS destination_id
    ON CONFLICT (workspace_id, destination_id)
    DO UPDATE SET
        status = 'active',
        updated_at = EXCLUDED.updated_at;

    RETURN QUERY
    SELECT wd.*
    FROM public.workspace_destinations wd
    WHERE wd.workspace_id = p_target_workspace_id
      AND wd.destination_id = ANY (p_destination_ids)
      AND wd.status = 'active'
    ORDER BY wd.destination_id;
END;
$$;

REVOKE ALL
ON FUNCTION public.move_workspace_destination_memberships_authorized(
    BIGINT,
    BIGINT[],
    BIGINT
)
FROM PUBLIC, anon, authenticated;

GRANT EXECUTE
ON FUNCTION public.move_workspace_destination_memberships_authorized(
    BIGINT,
    BIGINT[],
    BIGINT
)
TO anon;

NOTIFY pgrst, 'reload schema';

COMMIT;
