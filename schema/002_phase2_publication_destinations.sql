CREATE TABLE IF NOT EXISTS publication_destinations (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(id) ON DELETE CASCADE,
    platform TEXT NOT NULL
        CHECK (platform IN ('telegram', 'bale')),
    destination_type TEXT NOT NULL
        CHECK (destination_type IN ('channel')),
    name TEXT NOT NULL,
    external_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'removed')),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
);

CREATE INDEX IF NOT EXISTS idx_publication_destinations_workspace_status
    ON publication_destinations (workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_publication_destinations_workspace_platform
    ON publication_destinations (workspace_id, platform);

CREATE UNIQUE INDEX IF NOT EXISTS publication_destinations_active_default_unique
    ON publication_destinations (workspace_id)
    WHERE is_default = TRUE AND status = 'active';

CREATE UNIQUE INDEX IF NOT EXISTS publication_destinations_workspace_platform_external_unique
    ON publication_destinations (workspace_id, platform, external_id)
    WHERE status <> 'removed';
