-- Keep the legacy tenant selectable alongside any number of workspaces.

ALTER TABLE user_workspace_preferences
    ADD COLUMN IF NOT EXISTS legacy_selected BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE user_workspace_preferences
SET legacy_selected = TRUE
WHERE context_type = 'legacy';
