-- One-time, explicit Telegram-to-Bale account linking.
CREATE TABLE IF NOT EXISTS public.bale_identity_link_codes (
    code_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    expires_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bale_identity_link_codes_user
    ON public.bale_identity_link_codes (user_id);

REVOKE ALL ON public.bale_identity_link_codes FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, DELETE ON public.bale_identity_link_codes TO service_role;

CREATE OR REPLACE FUNCTION public.consume_bale_identity_link(
    p_code_hash TEXT,
    p_bale_user_id BIGINT
) RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    link_row public.bale_identity_link_codes%ROWTYPE;
    target_row public.users%ROWTYPE;
    bale_row public.users%ROWTYPE;
    ref_record RECORD;
    has_reference BOOLEAN;
BEGIN
    IF p_bale_user_id IS NULL OR p_bale_user_id <= 0 THEN
        RETURN 'invalid';
    END IF;

    SELECT * INTO link_row FROM public.bale_identity_link_codes
    WHERE code_hash = p_code_hash FOR UPDATE;
    IF NOT FOUND OR link_row.expires_at <= EXTRACT(EPOCH FROM now()) THEN
        RETURN 'invalid';
    END IF;

    SELECT * INTO target_row FROM public.users
    WHERE id = link_row.user_id FOR UPDATE;
    IF NOT FOUND OR target_row.telegram_user_id IS NULL THEN
        RETURN 'invalid';
    END IF;

    IF target_row.bale_user_id IS NOT NULL THEN
        IF target_row.bale_user_id <> p_bale_user_id THEN
            RETURN 'conflict';
        END IF;
        DELETE FROM public.bale_identity_link_codes WHERE code_hash = p_code_hash;
        RETURN 'linked';
    END IF;

    SELECT * INTO bale_row FROM public.users
    WHERE bale_user_id = p_bale_user_id FOR UPDATE;
    IF FOUND THEN
        IF bale_row.telegram_user_id IS NOT NULL THEN
            RETURN 'conflict';
        END IF;
        -- Never discard a Bale-first account that already owns data.
        FOR ref_record IN
            SELECT n.nspname AS schema_name, c.relname AS table_name,
                   a.attname AS column_name
            FROM pg_constraint fk
            JOIN pg_class c ON c.oid = fk.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = fk.conkey[1]
            WHERE fk.contype = 'f'
              AND fk.confrelid = 'public.users'::regclass
              AND array_length(fk.conkey, 1) = 1
        LOOP
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I WHERE %I = $1)',
                           ref_record.schema_name, ref_record.table_name,
                           ref_record.column_name)
                INTO has_reference USING bale_row.id;
            IF has_reference THEN
                RETURN 'conflict';
            END IF;
        END LOOP;
        DELETE FROM public.users WHERE id = bale_row.id;
    END IF;

    UPDATE public.users SET bale_user_id = p_bale_user_id,
        updated_at = EXTRACT(EPOCH FROM now())
    WHERE id = target_row.id;
    DELETE FROM public.bale_identity_link_codes WHERE code_hash = p_code_hash;
    RETURN 'linked';
EXCEPTION WHEN unique_violation OR foreign_key_violation THEN
    RETURN 'conflict';
END;
$$;

REVOKE ALL ON FUNCTION public.consume_bale_identity_link(TEXT, BIGINT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.consume_bale_identity_link(TEXT, BIGINT)
    TO service_role;
