-- Branding sample capture and confirmation during workspace onboarding.

ALTER TABLE workspace_setup_state
    ADD COLUMN IF NOT EXISTS branding_sample_text TEXT,
    ADD COLUMN IF NOT EXISTS branding_sample_icons JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS branding_sample_status TEXT NOT NULL DEFAULT 'not_started';

ALTER TABLE workspace_setup_state
    DROP CONSTRAINT IF EXISTS workspace_setup_branding_sample_status_check;

ALTER TABLE workspace_setup_state
    ADD CONSTRAINT workspace_setup_branding_sample_status_check
    CHECK (branding_sample_status IN ('not_started', 'pending_confirmation', 'confirmed'));
