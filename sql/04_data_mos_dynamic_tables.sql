-- Recreate per-service tables with minimal base schema.
-- Dynamic JSON columns are added at load time by the collector.
-- WARNING: drops all rows in items_2855 .. items_62501.

DROP TABLE IF EXISTS data_mos.items_2855 CASCADE;
DROP TABLE IF EXISTS data_mos.items_2941 CASCADE;
DROP TABLE IF EXISTS data_mos.items_62461 CASCADE;
DROP TABLE IF EXISTS data_mos.items_62501 CASCADE;

CREATE TABLE data_mos.items_2855 (
    id         BIGSERIAL PRIMARY KEY,
    geom       GEOMETRY(Geometry, 4326),
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_data_mos_items_2855_geom ON data_mos.items_2855 USING GIST (geom);
CREATE INDEX idx_data_mos_items_2855_loaded_at ON data_mos.items_2855 (loaded_at DESC);

CREATE TABLE data_mos.items_2941 (
    id         BIGSERIAL PRIMARY KEY,
    geom       GEOMETRY(Geometry, 4326),
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_data_mos_items_2941_geom ON data_mos.items_2941 USING GIST (geom);
CREATE INDEX idx_data_mos_items_2941_loaded_at ON data_mos.items_2941 (loaded_at DESC);

CREATE TABLE data_mos.items_62461 (
    id         BIGSERIAL PRIMARY KEY,
    geom       GEOMETRY(Geometry, 4326),
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_data_mos_items_62461_geom ON data_mos.items_62461 USING GIST (geom);
CREATE INDEX idx_data_mos_items_62461_loaded_at ON data_mos.items_62461 (loaded_at DESC);

CREATE TABLE data_mos.items_62501 (
    id         BIGSERIAL PRIMARY KEY,
    geom       GEOMETRY(Geometry, 4326),
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_data_mos_items_62501_geom ON data_mos.items_62501 USING GIST (geom);
CREATE INDEX idx_data_mos_items_62501_loaded_at ON data_mos.items_62501 (loaded_at DESC);
