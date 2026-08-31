# Canonical Media Identity architecture

This document describes the additive, pre-cutover model.  It does not authorize
or execute a Production migration.

## Ownership boundaries

- `workspaces` are user-facing folders. Their names never enter publication
  output.
- `media_identities` own the media name, hashtag, channel tag, icons and format
  profile.
- `publication_destinations` are physical Telegram/Bale endpoints and are
  globally unique by `(platform, normalized_external_id)` while non-removed.
- `workspace_destinations` owns group placement. Current product semantics allow
  one active group per destination; moving changes only this association.
- `media_identity_members` grants media-level access. Publishing requires both
  an active Workspace role and an active Media role.

Readiness is independent at each layer: the group must be active and selected;
the association active; the destination active and verified; the media identity
active; and both access checks valid. Workspace branding/setup is not a
publication-readiness requirement in canonical mode.

## Branding resolution

Canonical publishing resolves Media Identity branding first, then an explicit
destination/platform override. Workspace branding remains compatibility-only
until backfill is validated. Moving a destination cannot update its Media
Identity, destination override, verification, message links or history.

## Staged backfill

1. Export a read-only snapshot.
2. Provide an explicit reviewed mapping with a stable `media_key`, user access,
   target group and physical endpoints.
3. Run `scripts/plan_canonical_media_backfill.py`. It is offline-only, defaults
   to dry-run, reports conflicts and emits rollback metadata.
4. Reject ambiguous ownership, one endpoint mapped to different media identities,
   or unverified access.
5. Apply an approved plan in one short transaction, verify canonical uniqueness,
   access, associations and ready targets, then commit.
6. Enable canonical runtime only after schema and data verification. Legacy
   selection is suppressed per user only when all of that user's Legacy physical
   targets are canonical, verified and authorized.

No tenant, Legacy column, history, Message Link, retry or idempotency row is
deleted during the first cutover.

## Production mapping intent (not executed)

- `Donya24News_En`: migrate Workspace 3 branding into one Media Identity; keep
  destination ids 3/4 and associate them with group 6 (`سیاسی`).
- `Donya24News`: create/reuse one Media Identity after review, then canonicalize
  Telegram and Bale independently.
- `@donya24_news`: create one Bale destination. Add user 2/user 3 grants only
  from an explicitly verified ownership/access mapping.
- `Farda No`, `Beneshaneh`, and `Siasat24`: derive separate Media Identities from
  their reviewed valid branding without changing existing destination ids.
- Workspace 3 stays in the database and is hidden while it has no active
  destination association.

## Security follow-up

Threats include forged callback ids, Workspace-only privilege escalation,
Media-only privilege escalation, cross-user claiming of a physical endpoint,
and direct Data API access. Runtime authorization checks both membership layers
server-side and transactional functions are executable only by `service_role`.
The migration revokes `anon`/`authenticated` access to new tables.

Production RLS remains a separate approved project. Future policies should map
the authenticated principal to `users`, allow reads only through active
Workspace/Media memberships, restrict writes to owner/manager roles, and include
both `USING` and `WITH CHECK` for updates. Service credentials must remain
server-side. Do not enable RLS on Production without complete policies and a
service-path regression test.
