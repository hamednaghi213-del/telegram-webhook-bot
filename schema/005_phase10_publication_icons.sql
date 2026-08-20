-- Phase 10: flexible Unicode publication icons for workspace branding.

ALTER TABLE workspace_branding
    ADD COLUMN IF NOT EXISTS publication_icons JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS icons_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE destination_branding
    ADD COLUMN IF NOT EXISTS publication_icons JSONB,
    ADD COLUMN IF NOT EXISTS icons_enabled BOOLEAN;

-- Preserve the established Donya24 style without imposing it on other workspaces.
UPDATE workspace_branding
SET publication_icons = '["❇️", "🔹"]'::jsonb,
    icons_enabled = TRUE,
    updated_at = EXTRACT(EPOCH FROM NOW())
WHERE media_name = 'دنیا۲۴'
  AND publication_icons = '[]'::jsonb;
