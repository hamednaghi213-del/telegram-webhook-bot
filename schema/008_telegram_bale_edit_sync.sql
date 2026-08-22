-- Persist Telegram/Bale message pairs so safe Telegram edits can be mirrored.

CREATE TABLE IF NOT EXISTS publication_message_links (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    telegram_destination_id BIGINT NOT NULL
        REFERENCES publication_destinations(id) ON DELETE CASCADE,
    telegram_chat_id TEXT NOT NULL,
    telegram_message_id BIGINT NOT NULL,
    bale_destination_id BIGINT NOT NULL
        REFERENCES publication_destinations(id) ON DELETE CASCADE,
    bale_chat_id TEXT NOT NULL,
    bale_message_id BIGINT NOT NULL,
    content_kind TEXT NOT NULL CHECK (content_kind IN ('text', 'caption')),
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    UNIQUE (telegram_chat_id, telegram_message_id)
);

CREATE INDEX IF NOT EXISTS idx_publication_message_links_workspace
    ON publication_message_links (workspace_id, created_at DESC);

