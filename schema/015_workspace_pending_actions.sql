BEGIN;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS pending_workspace_action TEXT NULL,
    ADD COLUMN IF NOT EXISTS pending_workspace_id BIGINT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_pending_workspace_action_check'
          AND conrelid = 'public.users'::regclass
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_pending_workspace_action_check
            CHECK (
                pending_workspace_action IS NULL
                OR pending_workspace_action IN (
                    'create_workspace_name',
                    'rename_workspace'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_pending_workspace_id_fkey'
          AND conrelid = 'public.users'::regclass
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_pending_workspace_id_fkey
            FOREIGN KEY (pending_workspace_id)
            REFERENCES public.workspaces(id)
            ON DELETE SET NULL;
    END IF;
END
$$;

NOTIFY pgrst, 'reload schema';
COMMIT;
