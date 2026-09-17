-- =========================================================
-- 029 — BALE USER IDENTITY (Bale Full Bot Parity, slice 1)
-- =========================================================
--
-- Adds an explicit Bale identity column to the shared users
-- table. A Bale numeric user ID is a SEPARATE identity space
-- from Telegram numeric user IDs: it must never be treated as
-- equivalent to a Telegram ID.
--
-- - bale_user_id is nullable: Telegram-originated users keep
--   NULL and continue to resolve by telegram_user_id.
-- - A partial UNIQUE index enforces one Bale identity per user
--   while still allowing any number of NULL rows.
-- - Association of a Bale identity with an EXISTING account is
--   an explicit operation performed by the application
--   (link_bale_identity); it is never inferred numerically.
--
-- The migration is additive and rollback-safe: no existing
-- column, table or RPC is altered beyond the new nullable
-- column and its index.
-- =========================================================

BEGIN;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS bale_user_id BIGINT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_bale_user_id
    ON public.users (bale_user_id)
    WHERE bale_user_id IS NOT NULL;

COMMIT;
