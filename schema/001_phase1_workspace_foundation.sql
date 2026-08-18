-- ==========================================================
-- Phase 1 — Workspace Foundation
-- Migration: 001_phase1_workspace_foundation.sql
--
-- ADDITIVE ONLY — does not alter or remove any existing tables.
-- Safe to apply to current production data.
-- Tenant system (tenants table) is untouched.
-- ==========================================================

-- ----------------------------------------------------------
-- Users
-- Preserves Telegram compatibility.
-- telegram_id is NOT the primary key to allow future
-- non-Telegram identity providers and owner transfer flows.
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS ws_users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id   BIGINT      UNIQUE NOT NULL,
    first_name    TEXT,
    last_name     TEXT,
    username      TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------
-- Workspaces
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS ws_workspaces (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,
    owner_user_id UUID        NOT NULL REFERENCES ws_users(id) ON DELETE RESTRICT,
    status        TEXT        NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'suspended', 'archived')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ws_workspaces_owner
    ON ws_workspaces (owner_user_id);

-- ----------------------------------------------------------
-- Workspace Members
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS ws_workspace_members (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID        NOT NULL REFERENCES ws_workspaces(id) ON DELETE CASCADE,
    user_id       UUID        NOT NULL REFERENCES ws_users(id) ON DELETE CASCADE,
    role          TEXT        NOT NULL
                              CHECK (role IN ('owner', 'manager', 'publisher', 'writer')),
    status        TEXT        NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'suspended', 'removed')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_workspace_member UNIQUE (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_ws_members_workspace
    ON ws_workspace_members (workspace_id);

CREATE INDEX IF NOT EXISTS idx_ws_members_user
    ON ws_workspace_members (user_id);
