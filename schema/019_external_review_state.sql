-- =========================================================
-- EXTERNAL CONTENT REVIEW STATE
-- =========================================================
--
-- Durable pending state for External Content Review.
--
-- Purpose:
--   - survive Render worker/process changes
--   - survive ordinary application restarts
--   - allow Telegram callback requests to resolve the
--     preview created by a previous webhook request
--
-- This table stores transport-neutral normalized content.
-- Publication itself remains in the Shared Publication Engine.
-- =========================================================


create table if not exists public.external_review_state (
    review_id text primary key,

    chat_id bigint not null,

    content jsonb not null,

    created_at timestamptz not null
        default now(),

    expires_at timestamptz not null
);


-- =========================================================
-- ONE ACTIVE REVIEW PER CHAT
-- =========================================================
--
-- Current review UX intentionally replaces an older pending
-- preview when the user submits a new external URL.
-- =========================================================

create unique index if not exists
    external_review_state_chat_id_uidx
on public.external_review_state (
    chat_id
);


-- =========================================================
-- EXPIRATION LOOKUP
-- =========================================================

create index if not exists
    external_review_state_expires_at_idx
on public.external_review_state (
    expires_at
);


-- =========================================================
-- BASIC INTEGRITY
-- =========================================================

alter table public.external_review_state
    drop constraint if exists
        external_review_state_review_id_not_blank;

alter table public.external_review_state
    add constraint
        external_review_state_review_id_not_blank
    check (
        length(
            btrim(review_id)
        ) > 0
    );


alter table public.external_review_state
    drop constraint if exists
        external_review_state_content_object;

alter table public.external_review_state
    add constraint
        external_review_state_content_object
    check (
        jsonb_typeof(content) = 'object'
    );


alter table public.external_review_state
    drop constraint if exists
        external_review_state_expiry_after_creation;

alter table public.external_review_state
    add constraint
        external_review_state_expiry_after_creation
    check (
        expires_at > created_at
    );


-- =========================================================
-- ROW LEVEL SECURITY
-- =========================================================
--
-- Application access is through the server-side Supabase
-- service client. No direct anonymous/client access should
-- be allowed to pending editorial material.
-- =========================================================

alter table public.external_review_state
    enable row level security;


-- =========================================================
-- DOCUMENTATION
-- =========================================================

comment on table public.external_review_state is
    'Durable pending state for external-content review callbacks.';

comment on column public.external_review_state.review_id is
    'Opaque external review identifier used in callback_data.';

comment on column public.external_review_state.chat_id is
    'Interaction chat/user scope owning this pending review.';

comment on column public.external_review_state.content is
    'Serialized transport-neutral NormalizedExternalContent.';

comment on column public.external_review_state.created_at is
    'Time this pending external review was created.';

comment on column public.external_review_state.expires_at is
    'Time after which this pending review must no longer be accepted.';
