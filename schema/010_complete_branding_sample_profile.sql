-- Preserve every branding element and its semantic role from the approved sample.

ALTER TABLE workspace_setup_state
    ADD COLUMN IF NOT EXISTS branding_sample_profile JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE workspace_branding
    ADD COLUMN IF NOT EXISTS publication_profile JSONB NOT NULL DEFAULT '{}'::jsonb;
