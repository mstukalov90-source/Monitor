-- Add and maintain POINT geometry for reports from longitude/latitude.
-- Safe to run multiple times.
-- Priority: public.reports, fallback: lens.reports.

CREATE EXTENSION IF NOT EXISTS postgis;

DO $$
DECLARE
    target_table regclass := COALESCE(
        to_regclass('public.reports'),
        to_regclass('lens.reports')
    );
BEGIN
    IF target_table IS NULL THEN
        RAISE NOTICE 'Skipping migration: neither public.reports nor lens.reports exists.';
        RETURN;
    END IF;

    -- 1) Add geometry column if missing.
    EXECUTE format(
        'ALTER TABLE %s ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)',
        target_table
    );

    -- 2) Backfill geometry for existing rows.
    -- Rules:
    -- - NULL latitude/longitude -> geom = NULL
    -- - Invalid ranges -> geom = NULL
    -- - Valid coordinates -> POINT(longitude, latitude) in SRID 4326
    EXECUTE format($sql$
        UPDATE %s
        SET geom = CASE
            WHEN latitude IS NULL OR longitude IS NULL THEN NULL
            WHEN latitude < -90 OR latitude > 90 THEN NULL
            WHEN longitude < -180 OR longitude > 180 THEN NULL
            ELSE ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        END
    $sql$, target_table);
END
$$;

-- 3) Trigger function to keep geom in sync on INSERT/UPDATE.
CREATE OR REPLACE FUNCTION public.reports_set_geom_from_lon_lat()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.latitude IS NULL OR NEW.longitude IS NULL THEN
        NEW.geom := NULL;
        RETURN NEW;
    END IF;

    IF NEW.latitude < -90 OR NEW.latitude > 90
       OR NEW.longitude < -180 OR NEW.longitude > 180 THEN
        NEW.geom := NULL;

        -- Optional warning in PostgreSQL logs for invalid coordinates.
        RAISE WARNING 'reports: invalid coordinates (longitude=%, latitude=%), geom set to NULL',
            NEW.longitude, NEW.latitude;

        RETURN NEW;
    END IF;

    NEW.geom := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
    RETURN NEW;
END;
$$;

-- 4) Recreate trigger and index idempotently on the target reports table.
DO $$
DECLARE
    target_table regclass := COALESCE(
        to_regclass('public.reports'),
        to_regclass('lens.reports')
    );
BEGIN
    IF target_table IS NULL THEN
        RETURN;
    END IF;

    EXECUTE format(
        'DROP TRIGGER IF EXISTS trg_reports_set_geom_from_lon_lat ON %s',
        target_table
    );

    EXECUTE format($sql$
        CREATE TRIGGER trg_reports_set_geom_from_lon_lat
        BEFORE INSERT OR UPDATE OF longitude, latitude
        ON %s
        FOR EACH ROW
        EXECUTE FUNCTION public.reports_set_geom_from_lon_lat()
    $sql$, target_table);

    -- 5) Add spatial index for GIS queries.
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_reports_geom_gist ON %s USING GIST (geom)',
        target_table
    );
END
$$;
