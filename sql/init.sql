CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS data_mos;
CREATE SCHEMA IF NOT EXISTS lens;
CREATE SCHEMA IF NOT EXISTS stroymonitoring;
CREATE SCHEMA IF NOT EXISTS genplan;

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

-- genplan response_*.json storage (flattened columns)
CREATE TABLE IF NOT EXISTS genplan.responses (
    id                  BIGSERIAL PRIMARY KEY,
    file_name           TEXT NOT NULL,
    opening             BOOLEAN,
    legal               BOOLEAN,
    description         TEXT,
    image               TEXT,
    photo_lat           DOUBLE PRECISION,
    photo_lng           DOUBLE PRECISION,
    photo_azimuth_deg   INTEGER,
    order_source        TEXT,
    order_doc_num       TEXT,
    order_work_types    TEXT,
    order_date_start    DATE,
    order_date_end      DATE,
    order_customer      TEXT,
    order_status        TEXT,
    yolo_label          INTEGER,
    yolo_votes          JSONB,
    geom                GEOMETRY(Geometry, 4326),
    photo_geom          GEOMETRY(Point, 4326),
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genplan_responses_geom
    ON genplan.responses USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_genplan_responses_photo_geom
    ON genplan.responses USING GIST (photo_geom);
CREATE INDEX IF NOT EXISTS idx_genplan_responses_file_name
    ON genplan.responses (file_name);
CREATE INDEX IF NOT EXISTS idx_genplan_responses_loaded_at
    ON genplan.responses (loaded_at DESC);

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
