-- Allow a Bale-only account in the shared users table.
-- The existing UNIQUE constraint on telegram_user_id continues to
-- enforce uniqueness for every non-null Telegram ID.
BEGIN;

ALTER TABLE public.users
    ALTER COLUMN telegram_user_id DROP NOT NULL;

COMMIT;
