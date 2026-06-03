-- Shell tables for data_mos geometry split (points / lines / polygons per service).
-- Dynamic attribute columns are added by collector on first rebuild.
-- Safe to run multiple times.

CREATE SCHEMA IF NOT EXISTS data_mos;

DO $$
DECLARE
    base text;
    targets text[] := ARRAY[
        'items_2855', 'items_62441', 'items_62461', 'items_62501'
    ];
    suffix text;
    qualified text;
BEGIN
    FOREACH base IN ARRAY targets
    LOOP
        FOREACH suffix IN ARRAY ARRAY['_points', '_lines', '_polygons']
        LOOP
            qualified := format('data_mos.%I', base || suffix);
            EXECUTE format($sql$
                CREATE TABLE IF NOT EXISTS %s (
                    id         BIGSERIAL PRIMARY KEY,
                    geom       GEOMETRY(Geometry, 4326),
                    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    source_id  BIGINT
                )
            $sql$, qualified);

            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS %I ON %s USING GIST (geom)',
                'idx_' || base || suffix || '_geom',
                qualified
            );
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS %I ON %s (source_id)',
                'idx_' || base || suffix || '_source_id',
                qualified
            );
        END LOOP;

        qualified := format('data_mos.%I', base || '_polygons');
        EXECUTE format(
            'ALTER TABLE %s ADD COLUMN IF NOT EXISTS derived_from_id BIGINT',
            qualified
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %s (derived_from_id) '
            'WHERE derived_from_id IS NOT NULL',
            'idx_' || base || '_polygons_derived_from_id',
            qualified
        );
    END LOOP;
END
$$;
