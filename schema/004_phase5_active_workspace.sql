-- Phase 5: Persist the active workspace selected by each user.

CREATE TABLE IF NOT EXISTS user_workspace_preferences (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    active_workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_workspace_preferences_active_workspace
    ON user_workspace_preferences(active_workspace_id);

