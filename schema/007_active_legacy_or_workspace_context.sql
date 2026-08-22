-- Allow a user who has both a legacy tenant and workspace memberships to
-- explicitly choose which media context is active.

ALTER TABLE user_workspace_preferences
    ALTER COLUMN active_workspace_id DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS context_type TEXT NOT NULL DEFAULT 'workspace';

ALTER TABLE user_workspace_preferences
    DROP CONSTRAINT IF EXISTS user_workspace_preferences_context_check;

ALTER TABLE user_workspace_preferences
    ADD CONSTRAINT user_workspace_preferences_context_check
    CHECK (
        (context_type = 'workspace' AND active_workspace_id IS NOT NULL)
        OR
        (context_type = 'legacy' AND active_workspace_id IS NULL)
    );
