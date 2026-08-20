# Production release checklist

Phase 8 prepares the repository for release but does not perform deployment.

## Required configuration

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_SECRET_TOKEN` (random, private, and also supplied to Telegram when setting the webhook)
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `BALE_BOT_TOKEN` when optional Bale publishing is enabled
- `GEMINI_API_KEY` when Gemini summarization is enabled
- `ENABLE_SELF_PING=true` only when the hosting platform genuinely requires it
- `SELF_PING_URL` when self-ping is enabled

Never commit real values. Configure them in the deployment platform's secret store.

## Database

Back up the production database, then apply the migrations exactly once in order:

1. `schema/001_phase1_workspace_foundation.sql`
2. `schema/002_phase2_publication_destinations.sql`
3. `schema/003_phase4a_workspace_setup.sql`
4. `schema/004_phase5_active_workspace.sql`
5. `schema/005_phase10_publication_icons.sql`

The migration files are additive and use `IF NOT EXISTS`, but a backup is still required.

## Pre-deployment verification

1. Run `python -m pytest -q` and require a completely green result.
2. Start the service with production-like environment variables.
3. Require `GET /healthz` to return HTTP 200.
4. Require `GET /readyz` to return HTTP 200 after initialization.
5. Confirm the webhook rejects a missing or invalid secret header.

## Deployment and acceptance

1. Deploy one application instance (the project keeps media-group state in memory).
2. Set the Telegram webhook with the same `TELEGRAM_SECRET_TOKEN`.
3. Verify onboarding, channel verification, workspace switching, member management,
   destination selection, and one real publication.
4. Check application logs without exposing tokens or message contents.

## Rollback

1. Keep the previous application revision available.
2. If acceptance fails, restore the previous revision and webhook target.
3. Do not delete the additive workspace tables during application rollback.
4. Restore the database backup only for confirmed data corruption.
