-- =========================================================
-- Phase 1: Workspace Foundation
-- Migration: 001_phase1_workspace_foundation.sql
--
-- ADDITIVE ONLY — does not modify, rename, or drop any
-- existing production tables or columns.
-- Safe to run against current production schema.
-- =========================================================

-- ---------------------------------------------------------
-- users
-- Stores Telegram-compatible user identity.
-- telegram_user_id is NOT the primary key, allowing future
-- owner-transfer and multi-account scenarios.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                BIGSERIAL    PRIMARY KEY,
    telegram_user_id  BIGINT       NOT NULL UNIQUE,
    username          TEXT,
    first_name        TEXT,
    last_name         TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_user_id
    ON users (telegram_user_id);

-- ---------------------------------------------------------
-- workspaces
-- A workspace belongs to one owner (users.id) but
-- ownership can be transferred in future migrations.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS workspaces (
    id            BIGSERIAL    PRIMARY KEY,
    name          TEXT         NOT NULL,
    owner_user_id BIGINT       NOT NULL REFERENCES users(id),
    status        TEXT         NOT NULL DEFAULT 'active'
                               CHECK (status IN ('active', 'suspended', 'archived')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner_user_id
    ON workspaces (owner_user_id);

-- ---------------------------------------------------------
-- workspace_members
-- Maps users to workspaces with a role and a status.
-- One user may appear in many workspaces; many users may
-- appear in one workspace.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS workspace_members (
    id            BIGSERIAL    PRIMARY KEY,
    workspace_id  BIGINT       NOT NULL REFERENCES workspaces(id),
    user_id       BIGINT       NOT NULL REFERENCES users(id),
    role          TEXT         NOT NULL
                               CHECK (role IN ('owner', 'manager', 'publisher', 'writer')),
    status        TEXT         NOT NULL DEFAULT 'active'
                               CHECK (status IN ('active', 'suspended', 'removed')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace_id
    ON workspace_members (workspace_id);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id
    ON workspace_members (user_id);
