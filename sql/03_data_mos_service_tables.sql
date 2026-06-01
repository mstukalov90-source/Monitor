-- Per-service data.mos.ru tables (same layout as data_mos.items).

CREATE TABLE IF NOT EXISTS data_mos.items_2855 (
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

CREATE INDEX IF NOT EXISTS idx_data_mos_items_2855_geom
    ON data_mos.items_2855 USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_2855_order_number
    ON data_mos.items_2855 (order_number);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_2855_loaded_at
    ON data_mos.items_2855 (loaded_at DESC);

CREATE TABLE IF NOT EXISTS data_mos.items_2941 (
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

CREATE INDEX IF NOT EXISTS idx_data_mos_items_2941_geom
    ON data_mos.items_2941 USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_2941_order_number
    ON data_mos.items_2941 (order_number);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_2941_loaded_at
    ON data_mos.items_2941 (loaded_at DESC);

CREATE TABLE IF NOT EXISTS data_mos.items_62461 (
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

CREATE INDEX IF NOT EXISTS idx_data_mos_items_62461_geom
    ON data_mos.items_62461 USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_62461_order_number
    ON data_mos.items_62461 (order_number);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_62461_loaded_at
    ON data_mos.items_62461 (loaded_at DESC);

CREATE TABLE IF NOT EXISTS data_mos.items_62501 (
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

CREATE INDEX IF NOT EXISTS idx_data_mos_items_62501_geom
    ON data_mos.items_62501 USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_62501_order_number
    ON data_mos.items_62501 (order_number);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_62501_loaded_at
    ON data_mos.items_62501 (loaded_at DESC);
