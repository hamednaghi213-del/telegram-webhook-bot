# Legacy to Workspace cutover runbook

This runbook is intentionally non-executable. Production changes require a
separate approved, transaction-scoped backfill after the dry-run inventory is
reviewed.

## Ordering

1. Lock the tenant and target workspace rows in one transaction.
2. Re-read the raw Telegram user to `users.id` mapping and active owner/manager
   membership. Never treat the raw Telegram id as the internal user id.
3. Normalize each physical destination as `(platform, identifier without @,
   casefolded)` and reject cross-user ownership ambiguity.
4. Reuse a canonical row when one exists; otherwise insert one canonical
   `publication_destinations` row. Telegram and Bale are independent.
5. Preserve destination status, verification, branding, message links and all
   history. Do not rewrite historical identities.
6. Ensure the target Workspace is selected. Do not remove other selections.
7. Only after every meaningful destination of that tenant has a canonical row,
   set `legacy_selected=false`. Keep the tenant row intact.
8. Commit only if postconditions prove one target per canonical identity.

## Production blockers found in the read-only inventory

- Tenant 1 / users.id 3: Telegram `@Donya24News` has no canonical row.
- Tenant 1 / users.id 3: Bale `@donya24_news` has no canonical row, but the same
  Legacy Bale identifier is also present on tenant 2. Ownership must be
  resolved before either row is claimed.
- Workspace 6 (`سیاسی`) is selected but has incomplete setup and no workspace
  branding. Legacy branding must not silently overwrite the intended branding
  of this group. The migration approval must specify whether to finish its
  branding first or claim into a different completed canonical Workspace.
- Tenant 5 / users.id 1: both `@farda_no` identities already exist canonically
  in Workspace 1; create zero destination rows and suppress only the compatible
  Legacy selection after verification.
- Tenant 2 / users.id 2: Telegram `@channel` is a placeholder and must never be
  migrated.

## Rollback

Before the transaction, record inserted destination ids and the previous
preference/selection rows. Rollback deletes only destination rows inserted by
that transaction and restores only preference/selection values changed by that
transaction. Existing tenant, Workspace, membership, branding, history,
verification and message-link rows are never deleted or rewritten.
