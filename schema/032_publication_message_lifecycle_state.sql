-- Keep lifecycle retry and echo state on the existing B11 message index.
-- No second publication mapping is created.
BEGIN;

ALTER TABLE public.publication_delivery_message_index
    ADD COLUMN IF NOT EXISTS part_ordinal INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS edit_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS edit_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (edit_status IN ('pending', 'sending', 'succeeded', 'failed')),
    ADD COLUMN IF NOT EXISTS edit_attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (edit_attempt_count >= 0),
    ADD COLUMN IF NOT EXISTS edit_lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS delete_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (delete_status IN ('pending', 'sending', 'succeeded', 'failed')),
    ADD COLUMN IF NOT EXISTS delete_attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (delete_attempt_count >= 0),
    ADD COLUMN IF NOT EXISTS delete_lease_expires_at TIMESTAMPTZ;

-- Existing album rows retain their insertion order. New rows receive the
-- ordinal directly from the ordered transport response.
WITH numbered AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY delivery_id, part_key ORDER BY id
           ) - 1 AS ordinal
    FROM public.publication_delivery_message_index
)
UPDATE public.publication_delivery_message_index AS item
SET part_ordinal = numbered.ordinal
FROM numbered
WHERE item.id = numbered.id
  AND item.part_ordinal <> numbered.ordinal;

COMMIT;
