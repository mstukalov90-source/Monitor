CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS data_mos;
CREATE SCHEMA IF NOT EXISTS lens;
CREATE SCHEMA IF NOT EXISTS stroymonitoring;
CREATE SCHEMA IF NOT EXISTS genplan;
CREATE SCHEMA IF NOT EXISTS odh_export;

-- ogh-disruption table shell: sql/11_odh_export_ogh_disruption.sql (mounted in docker-compose initdb)

-- data.mos.ru export storage (flattened columns)
CREATE TABLE IF NOT EXISTS data_mos.items (
    id                          BIGSERIAL PRIMARY KEY,
    dataset_id                  INTEGER,
    row_id                      TEXT,
    version_number              TEXT,
    release_number              TEXT,
    order_number                TEXT,
    order_date                  TEXT,
    customer_construction       TEXT,
    customer_construction_inn   TEXT,
    general_contractor          TEXT,
    general_contractor_inn      TEXT,
    work_type                   JSONB,
    order_work                  JSONB,
    earthwork_objectives        JSONB,
    objectives_temp_fences      JSONB,
    objectives_temp_objects     JSONB,
    address_nearby_building     TEXT,
    adm_area                    TEXT,
    district                    TEXT,
    work_place_description      TEXT,
    work_start_date             TEXT,
    work_end_date               TEXT,
    global_id                   BIGINT,
    geom                        GEOMETRY(Geometry, 4326),
    loaded_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_mos_items_geom
    ON data_mos.items USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_order_number
    ON data_mos.items (order_number);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_loaded_at
    ON data_mos.items (loaded_at DESC);

-- Per-service tables: sql/04_data_mos_dynamic_tables.sql (mounted in docker-compose initdb)

-- genplan jsons_genplan/*.json — shells; dynamic columns added by genplan_job
-- Full migration for existing DBs: sql/10_genplan_multi_tables.sql

CREATE TABLE IF NOT EXISTS genplan."order" (
    id          BIGSERIAL PRIMARY KEY,
    file_name   TEXT NOT NULL,
    geom        GEOMETRY(Geometry, 4326),
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genplan_order_geom
    ON genplan."order" USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_genplan_order_file_name
    ON genplan."order" (file_name);
CREATE INDEX IF NOT EXISTS idx_genplan_order_loaded_at
    ON genplan."order" (loaded_at DESC);

CREATE TABLE IF NOT EXISTS genplan.photo_meta (
    id          BIGSERIAL PRIMARY KEY,
    file_name   TEXT NOT NULL,
    geom        GEOMETRY(Point, 4326),
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genplan_photo_meta_geom
    ON genplan.photo_meta USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_genplan_photo_meta_file_name
    ON genplan.photo_meta (file_name);
CREATE INDEX IF NOT EXISTS idx_genplan_photo_meta_loaded_at
    ON genplan.photo_meta (loaded_at DESC);

CREATE TABLE IF NOT EXISTS genplan.upload (
    id          BIGSERIAL PRIMARY KEY,
    file_name   TEXT NOT NULL,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genplan_upload_file_name
    ON genplan.upload (file_name);
CREATE INDEX IF NOT EXISTS idx_genplan_upload_loaded_at
    ON genplan.upload (loaded_at DESC);

CREATE TABLE IF NOT EXISTS genplan.uuid_area (
    id          BIGSERIAL PRIMARY KEY,
    file_name   TEXT NOT NULL,
    uuid        TEXT,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genplan_uuid_area_uuid
    ON genplan.uuid_area (uuid);
CREATE INDEX IF NOT EXISTS idx_genplan_uuid_area_file_name
    ON genplan.uuid_area (file_name);
CREATE INDEX IF NOT EXISTS idx_genplan_uuid_area_loaded_at
    ON genplan.uuid_area (loaded_at DESC);

-- lens schema tables are created dynamically by lens_sync_job

CREATE SCHEMA IF NOT EXISTS collector;

CREATE TABLE IF NOT EXISTS collector.job_runs (
    id              BIGSERIAL PRIMARY KEY,
    job_name        TEXT NOT NULL,
    status          TEXT NOT NULL,
    message         TEXT,
    rows_affected   BIGINT DEFAULT 0,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_job_runs_job_name
    ON collector.job_runs (job_name, started_at DESC);
