-- Helpers for data_mos archival purge (date/year parsing from TEXT columns).

CREATE SCHEMA IF NOT EXISTS data_mos;

CREATE OR REPLACE FUNCTION data_mos.parse_text_date(value text)
RETURNS date
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    trimmed text;
BEGIN
    IF value IS NULL THEN
        RETURN NULL;
    END IF;
    trimmed := btrim(value);
    IF trimmed = '' THEN
        RETURN NULL;
    END IF;

    IF trimmed ~ '^\d{4}-\d{2}-\d{2}' THEN
        BEGIN
            RETURN trimmed::date;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END IF;

    IF trimmed ~ '^\d{2}\.\d{2}\.\d{4}$' THEN
        BEGIN
            RETURN to_date(trimmed, 'DD.MM.YYYY');
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END IF;

    IF trimmed ~ '^\d{2}\.\d{2}\.\d{2}$' THEN
        BEGIN
            RETURN to_date(trimmed, 'DD.MM.YY');
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END IF;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION data_mos.extract_year(value text)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    trimmed text;
    match text;
BEGIN
    IF value IS NULL THEN
        RETURN NULL;
    END IF;
    trimmed := btrim(value);
    IF trimmed = '' THEN
        RETURN NULL;
    END IF;

    match := substring(trimmed from '(\d{4})');
    IF match IS NULL THEN
        RETURN NULL;
    END IF;

    BEGIN
        RETURN match::integer;
    EXCEPTION WHEN OTHERS THEN
        RETURN NULL;
    END;
END;
$$;
