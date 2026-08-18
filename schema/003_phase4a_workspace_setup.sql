-- Phase 4A: Workspace Setup State, Branding, and Destination Verification
-- Additive only — no existing tables modified.

-- =========================================================
-- WORKSPACE SETUP STATE
-- Tracks one-time setup progress (not_started / in_progress / completed).
-- One row per workspace; safe to upsert repeatedly.
-- =========================================================

CREATE TABLE IF NOT EXISTS workspace_setup_state (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(id) ON DELETE CASCADE,
    step TEXT NOT NULL DEFAULT 'not_started'
        CHECK (step IN ('not_started', 'in_progress', 'completed')),
    current_step_key TEXT,
    created_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),
    CONSTRAINT workspace_setup_state_workspace_unique
        UNIQUE (workspace_id)
);

-- =========================================================
-- WORKSPACE BRANDING
-- Workspace-level branding: name, hashtag, channel tag.
-- Belongs to the workspace, NOT the Telegram user.
-- Designed to support future destination-level overrides.
-- Does NOT replace or touch legacy tenant branding columns.
-- =========================================================

CREATE TABLE IF NOT EXISTS workspace_branding (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL
        REFERENCES workspaces(id) ON DELETE CASCADE,
    media_name TEXT NOT NULL DEFAULT '',
    hashtag TEXT NOT NULL DEFAULT '',
    channel_tag TEXT NOT NULL DEFAULT '',
    created_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),
    CONSTRAINT workspace_branding_workspace_unique
        UNIQUE (workspace_id)
);

-- =========================================================
-- DESTINATION BRANDING
-- Per-destination branding: hashtag, channel_tag, optional custom_footer.
-- Overrides workspace_branding for the specific channel.
-- One row per destination; custom_footer is optional (may be NULL or empty).
-- Does NOT replace or touch workspace_branding or legacy tenant branding.
-- =========================================================

CREATE TABLE IF NOT EXISTS destination_branding (
    id BIGSERIAL PRIMARY KEY,
    destination_id BIGINT NOT NULL
        REFERENCES publication_destinations(id) ON DELETE CASCADE,
    hashtag TEXT NOT NULL DEFAULT '',
    channel_tag TEXT NOT NULL DEFAULT '',
    custom_footer TEXT,
    footer_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),
    CONSTRAINT destination_branding_destination_unique
        UNIQUE (destination_id)
);

-- =========================================================
-- DESTINATION VERIFICATION
-- Tracks whether a publication destination has been verified
-- (i.e. bot confirmed as admin of the Telegram channel).
-- Phase 4A: destinations are registered but NOT verified.
-- Phase 4B: verification via Telegram API will set verified=TRUE.
-- Unverified destinations are stored with status='inactive'
-- in publication_destinations and verified=FALSE here.
-- =========================================================

CREATE TABLE IF NOT EXISTS destination_verification (
    id BIGSERIAL PRIMARY KEY,
    destination_id BIGINT NOT NULL
        REFERENCES publication_destinations(id) ON DELETE CASCADE,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_note TEXT NOT NULL DEFAULT '',
    created_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION NOT NULL
        DEFAULT EXTRACT(EPOCH FROM NOW()),
    CONSTRAINT destination_verification_unique
        UNIQUE (destination_id)
);
