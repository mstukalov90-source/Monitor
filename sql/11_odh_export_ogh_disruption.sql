CREATE SCHEMA IF NOT EXISTS odh_export;

CREATE TABLE IF NOT EXISTS odh_export."ogh-disruption" (
    id           BIGSERIAL PRIMARY KEY,
    label_text   TEXT,
    filter_pass  TEXT,
    source_json  TEXT NOT NULL,
    lon          DOUBLE PRECISION NOT NULL,
    lat          DOUBLE PRECISION NOT NULL,
    geometry     GEOMETRY(Point, 4326) NOT NULL,
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ogh_disruption_source_coords
    ON odh_export."ogh-disruption" (source_json, lon, lat);

CREATE INDEX IF NOT EXISTS idx_ogh_disruption_geometry
    ON odh_export."ogh-disruption" USING GIST (geometry);
