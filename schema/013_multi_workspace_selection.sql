BEGIN;

CREATE TABLE IF NOT EXISTS user_selected_workspaces (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    PRIMARY KEY (user_id, workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_user_selected_workspaces_workspace
    ON user_selected_workspaces(workspace_id);

INSERT INTO user_selected_workspaces (user_id, workspace_id)
SELECT user_id, active_workspace_id
FROM user_workspace_preferences
WHERE context_type = 'workspace' AND active_workspace_id IS NOT NULL
ON CONFLICT (user_id, workspace_id) DO NOTHING;

NOTIFY pgrst, 'reload schema';
COMMIT;
