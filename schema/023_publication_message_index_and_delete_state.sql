BEGIN;

ALTER TABLE public.publication_deliveries
    ADD COLUMN IF NOT EXISTS delete_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            delete_status IN (
                'pending',
                'sending',
                'succeeded',
                'failed',
                'failed_terminal'
            )
        );

ALTER TABLE public.publication_deliveries
    ADD COLUMN IF NOT EXISTS delete_attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (delete_attempt_count >= 0);

ALTER TABLE public.publication_deliveries
    ADD COLUMN IF NOT EXISTS delete_last_error TEXT;

ALTER TABLE public.publication_deliveries
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS public.publication_delivery_message_index (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    delivery_id BIGINT NOT NULL
        REFERENCES public.publication_deliveries(id)
        ON DELETE CASCADE,
    platform TEXT NOT NULL,
    destination_chat_id TEXT NOT NULL DEFAULT '',
    part_key TEXT NOT NULL,
    message_id BIGINT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT publication_delivery_message_index_unique
        UNIQUE (platform, destination_chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS publication_delivery_message_index_delivery_idx
    ON public.publication_delivery_message_index (delivery_id);

CREATE INDEX IF NOT EXISTS publication_delivery_message_index_lookup_idx
    ON public.publication_delivery_message_index (
        platform,
        destination_chat_id,
        message_id
    );

CREATE INDEX IF NOT EXISTS publication_deliveries_delete_status_idx
    ON public.publication_deliveries (
        delete_status,
        deleted_at
    );

ALTER TABLE public.publication_delivery_message_index
    ENABLE ROW LEVEL SECURITY;

REVOKE ALL
ON TABLE public.publication_delivery_message_index
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON SEQUENCE public.publication_delivery_message_index_id_seq
FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.publication_delivery_message_index
TO service_role;

GRANT USAGE, SELECT
ON SEQUENCE public.publication_delivery_message_index_id_seq
TO service_role;

COMMIT;
