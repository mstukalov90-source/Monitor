-- CRM task area polygons (loaded from GeoJSON, e.g. раменки.geojson).

CREATE TABLE IF NOT EXISTS crm.tasks_area (
    key         UUID PRIMARY KEY,
    fid         BIGINT,
    gid         BIGINT,
    rayon       TEXT,
    okrug       TEXT,
    okrug_shor  TEXT,
    area        DOUBLE PRECISION,
    geom        GEOMETRY(Geometry, 4326),
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_tasks_area_geom
    ON crm.tasks_area USING GIST (geom);
