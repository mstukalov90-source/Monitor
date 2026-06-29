-- Migrate mggt_station tables: Geometry SRID 980077 -> 4326 (WGS84) and GPKG attribute columns.
-- Safe on fresh installs where sql/20 already creates geometry(..., 4326).

-- KGS tables (КГС.gpkg attributes)
ALTER TABLE mggt_station.kgs_point
    ADD COLUMN IF NOT EXISTS color text NULL;

ALTER TABLE mggt_station.kgs_lines
    ADD COLUMN IF NOT EXISTS color text NULL;

-- SPS tables (СПС GPKG attributes)
ALTER TABLE mggt_station.sps_point
    ADD COLUMN IF NOT EXISTS geometry_fme_type text NULL,
    ADD COLUMN IF NOT EXISTS color text NULL,
    ADD COLUMN IF NOT EXISTS svg_name text NULL,
    ADD COLUMN IF NOT EXISTS object_type text NULL,
    ADD COLUMN IF NOT EXISTS new_cell_name text NULL,
    ADD COLUMN IF NOT EXISTS utf8_cell_name text NULL,
    ADD COLUMN IF NOT EXISTS font integer NULL,
    ADD COLUMN IF NOT EXISTS text_group integer NULL,
    ADD COLUMN IF NOT EXISTS igds_style integer NULL,
    ADD COLUMN IF NOT EXISTS igds_level integer NULL,
    ADD COLUMN IF NOT EXISTS igds_justification integer NULL,
    ADD COLUMN IF NOT EXISTS igds_original_justification text NULL;

ALTER TABLE mggt_station.sps_lines
    ADD COLUMN IF NOT EXISTS geometry_fme_type text NULL,
    ADD COLUMN IF NOT EXISTS color text NULL,
    ADD COLUMN IF NOT EXISTS svg_name text NULL,
    ADD COLUMN IF NOT EXISTS object_type text NULL,
    ADD COLUMN IF NOT EXISTS new_cell_name text NULL,
    ADD COLUMN IF NOT EXISTS utf8_cell_name text NULL,
    ADD COLUMN IF NOT EXISTS font integer NULL,
    ADD COLUMN IF NOT EXISTS text_group integer NULL,
    ADD COLUMN IF NOT EXISTS igds_style integer NULL,
    ADD COLUMN IF NOT EXISTS igds_level integer NULL,
    ADD COLUMN IF NOT EXISTS igds_justification integer NULL,
    ADD COLUMN IF NOT EXISTS igds_original_justification text NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM geometry_columns
        WHERE f_table_schema = 'mggt_station'
          AND f_table_name = 'kgs_point'
          AND f_geometry_column = 'Geometry'
          AND srid = 980077
    ) THEN
        ALTER TABLE mggt_station.kgs_point
            ALTER COLUMN "Geometry" TYPE geometry(Point, 4326)
            USING ST_Transform(ST_SetSRID("Geometry", 980077), 4326);
    END IF;

    IF EXISTS (
        SELECT 1 FROM geometry_columns
        WHERE f_table_schema = 'mggt_station'
          AND f_table_name = 'kgs_lines'
          AND f_geometry_column = 'Geometry'
          AND srid = 980077
    ) THEN
        ALTER TABLE mggt_station.kgs_lines
            ALTER COLUMN "Geometry" TYPE geometry(Geometry, 4326)
            USING ST_Transform(ST_SetSRID("Geometry", 980077), 4326);
    END IF;

    IF EXISTS (
        SELECT 1 FROM geometry_columns
        WHERE f_table_schema = 'mggt_station'
          AND f_table_name = 'sps_point'
          AND f_geometry_column = 'Geometry'
          AND srid = 980077
    ) THEN
        ALTER TABLE mggt_station.sps_point
            ALTER COLUMN "Geometry" TYPE geometry(Point, 4326)
            USING ST_Transform(ST_SetSRID("Geometry", 980077), 4326);
    END IF;

    IF EXISTS (
        SELECT 1 FROM geometry_columns
        WHERE f_table_schema = 'mggt_station'
          AND f_table_name = 'sps_lines'
          AND f_geometry_column = 'Geometry'
          AND srid = 980077
    ) THEN
        ALTER TABLE mggt_station.sps_lines
            ALTER COLUMN "Geometry" TYPE geometry(Geometry, 4326)
            USING ST_Transform(ST_SetSRID("Geometry", 980077), 4326);
    END IF;
END $$;
