-- Genplan: drop legacy responses table, create four typed table shells.
-- Dynamic JSON columns are added at import time by genplan_job.

DROP TABLE IF EXISTS genplan.responses CASCADE;

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
