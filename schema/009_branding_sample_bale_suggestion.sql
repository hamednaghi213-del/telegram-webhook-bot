-- Persist an optional Bale channel discovered from the onboarding sample.

ALTER TABLE workspace_setup_state
    ADD COLUMN IF NOT EXISTS branding_sample_bale_url TEXT,
    ADD COLUMN IF NOT EXISTS branding_sample_bale_channel TEXT,
    ADD COLUMN IF NOT EXISTS branding_sample_bale_status TEXT NOT NULL DEFAULT 'none';

ALTER TABLE workspace_setup_state
    DROP CONSTRAINT IF EXISTS workspace_setup_branding_sample_bale_status_check;

ALTER TABLE workspace_setup_state
    ADD CONSTRAINT workspace_setup_branding_sample_bale_status_check
    CHECK (branding_sample_bale_status IN ('none', 'pending', 'connected', 'ignored'));

