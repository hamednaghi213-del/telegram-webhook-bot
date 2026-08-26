# Publication persistence proposal (not an executable migration)

Status: design only. This SQL has not been applied to Supabase and is deliberately
kept outside the schema/migrations directories.

## Guarantees and identity

`user_id` references the internal `public.users.id`; the Telegram account id is
stored separately. A source, destination delivery and each delivery part have
separate state. Album snapshots use `delivery_generation`, so completing an old
snapshot cannot suppress late members in a newer generation.

```sql
begin;

create table public.publication_sources (
  id bigint generated always as identity primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  telegram_user_id bigint,
  source_key text not null unique,
  source_kind text not null,
  delivery_generation integer not null default 1 check (delivery_generation > 0),
  status text not null default 'pending'
    check (status in ('pending','sending','partial','succeeded','failed','failed_terminal')),
  attempt_count integer not null default 0,
  last_error text,
  lease_owner text,
  lease_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.publication_deliveries (
  id bigint generated always as identity primary key,
  source_id bigint not null references public.publication_sources(id) on delete cascade,
  workspace_id bigint references public.workspaces(id) on delete set null,
  destination_id bigint references public.publication_destinations(id) on delete set null,
  platform text not null check (platform in ('telegram','bale')),
  destination_chat_id text not null,
  canonical_identity text not null,
  delivery_generation integer not null default 1 check (delivery_generation > 0),
  status text not null default 'pending'
    check (status in ('pending','sending','succeeded','failed','failed_terminal')),
  attempt_count integer not null default 0,
  last_error text,
  lease_owner text,
  lease_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_id, canonical_identity, delivery_generation)
);

create table public.publication_delivery_parts (
  id bigint generated always as identity primary key,
  delivery_id bigint not null references public.publication_deliveries(id) on delete cascade,
  part_key text not null,
  status text not null default 'pending'
    check (status in ('pending','sending','succeeded','failed','failed_terminal')),
  message_id bigint,
  destination_chat_id text,
  attempt_count integer not null default 0,
  last_error text,
  lease_owner text,
  lease_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (delivery_id, part_key)
);

create or replace function public.set_publication_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

create trigger publication_sources_updated_at before update on public.publication_sources
for each row execute function public.set_publication_updated_at();
create trigger publication_deliveries_updated_at before update on public.publication_deliveries
for each row execute function public.set_publication_updated_at();
create trigger publication_delivery_parts_updated_at before update on public.publication_delivery_parts
for each row execute function public.set_publication_updated_at();

create index publication_sources_lease_idx on public.publication_sources(status, lease_expires_at);
create index publication_deliveries_lease_idx on public.publication_deliveries(status, lease_expires_at);
create index publication_parts_lease_idx on public.publication_delivery_parts(status, lease_expires_at);

commit;
```

Atomic claims use one `update ... where status in (...) and (lease_expires_at is
null or lease_expires_at < now()) returning *` transaction. An expired lease is
recoverable by another worker. A successful part is never reclaimed.

## Crash and retry behaviour

- Restart after primary success: the primary part remains `succeeded`; resume at
  the first incomplete blockquote/follow-up.
- Restart during follow-up: expired part lease is reclaimed; completed parts are
  not sent again.
- Restart during album: the delivery generation identifies the exact batch;
  later members use the next generation.
- Duplicate webhook: `source_key` uniqueness returns the existing source.
- Second worker: conditional lease update permits one claimant only.
- Crash with open lease: retry begins after `lease_expires_at`.
- Telegram success/Bale failure: Telegram delivery remains succeeded; only Bale
  is retried and the source remains partial.
- One Workspace success/another failure: each canonical delivery is independent.
- Existing `publication_message_links` remains a Legacy compatibility projection;
  new multi-destination truth lives in delivery parts.

Rollback, if this proposal is later approved, drops only the three triggers,
three indexes, three new tables and `set_publication_updated_at()` function.

## Read-only verification for migrations 011-013

These queries are for a later, explicitly authorised Supabase inspection. They
have not been run in this change.

```sql
select table_name, column_name, is_nullable, column_default, data_type
from information_schema.columns
where table_schema='public'
  and ((table_name='user_workspace_preferences' and column_name in ('created_at','updated_at','legacy_selected'))
    or (table_name='tenants' and column_name='updated_at')
    or table_name='user_selected_workspaces')
order by table_name, ordinal_position;

select conrelid::regclass as table_name, conname, pg_get_constraintdef(oid)
from pg_constraint
where conrelid in ('public.user_workspace_preferences'::regclass,
                   'public.user_selected_workspaces'::regclass);

select trigger_name, event_object_table, action_statement
from information_schema.triggers
where event_object_schema='public'
  and event_object_table in ('tenants','user_workspace_preferences');

select count(*) filter (where created_at is null) as missing_created_at,
       count(*) filter (where updated_at is null) as missing_updated_at
from public.user_workspace_preferences;

select count(*) filter (where updated_at is null) as missing_updated_at
from public.tenants;

select user_id, workspace_id, count(*)
from public.user_selected_workspaces
group by user_id, workspace_id having count(*) > 1;
```
