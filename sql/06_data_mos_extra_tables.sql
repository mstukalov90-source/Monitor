-- Additional per-service tables (no DROP; safe on existing DB).

CREATE TABLE IF NOT EXISTS data_mos.items_1498 (
    id         BIGSERIAL PRIMARY KEY,
    geom       GEOMETRY(Geometry, 4326),
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_1498_geom
    ON data_mos.items_1498 USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_1498_loaded_at
    ON data_mos.items_1498 (loaded_at DESC);

CREATE TABLE IF NOT EXISTS data_mos.items_1500 (
    id         BIGSERIAL PRIMARY KEY,
    geom       GEOMETRY(Geometry, 4326),
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_1500_geom
    ON data_mos.items_1500 USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_1500_loaded_at
    ON data_mos.items_1500 (loaded_at DESC);

CREATE TABLE IF NOT EXISTS data_mos.items_2386 (
    id         BIGSERIAL PRIMARY KEY,
    geom       GEOMETRY(Geometry, 4326),
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_2386_geom
    ON data_mos.items_2386 USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_2386_loaded_at
    ON data_mos.items_2386 (loaded_at DESC);

CREATE TABLE IF NOT EXISTS data_mos.items_62441 (
    id         BIGSERIAL PRIMARY KEY,
    geom       GEOMETRY(Geometry, 4326),
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_62441_geom
    ON data_mos.items_62441 USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_data_mos_items_62441_loaded_at
    ON data_mos.items_62441 (loaded_at DESC);
