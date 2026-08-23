-- Make active-media preference upserts safe when PostgREST validates the
-- proposed INSERT row before applying ON CONFLICT.

BEGIN;

ALTER TABLE user_workspace_preferences
    ALTER COLUMN created_at
        SET DEFAULT EXTRACT(EPOCH FROM NOW()),
    ALTER COLUMN updated_at
        SET DEFAULT EXTRACT(EPOCH FROM NOW());

COMMIT;
