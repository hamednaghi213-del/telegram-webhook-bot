-- Phase 1: Workspace Foundation
-- Migration: 001_phase1_workspace_foundation.sql

-- =========================================================
-- USERS
-- =========================================================

CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL       PRIMARY KEY,
    telegram_id     BIGINT          NOT NULL UNIQUE,
    first_name      TEXT,
    last_name       TEXT,
    username        TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users (telegram_id);

-- =========================================================
-- WORKSPACES
-- =========================================================

CREATE TABLE IF NOT EXISTS workspaces (
    id          BIGSERIAL   PRIMARY KEY,
    name        TEXT        NOT NULL,
    slug        TEXT        NOT NULL UNIQUE,
    owner_id    BIGINT      NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner_id ON workspaces (owner_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_slug     ON workspaces (slug);

-- =========================================================
-- WORKSPACE MEMBERS
-- =========================================================

CREATE TYPE IF NOT EXISTS workspace_role   AS ENUM ('owner', 'manager', 'publisher', 'writer');
CREATE TYPE IF NOT EXISTS workspace_status AS ENUM ('active', 'suspended', 'removed');

CREATE TABLE IF NOT EXISTS workspace_members (
    id              BIGSERIAL           PRIMARY KEY,
    workspace_id    BIGINT              NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    user_id         BIGINT              NOT NULL REFERENCES users (id)      ON DELETE CASCADE,
    role            workspace_role      NOT NULL DEFAULT 'writer',
    status          workspace_status    NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_workspace_member UNIQUE (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace_id ON workspace_members (workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id      ON workspace_members (user_id);
