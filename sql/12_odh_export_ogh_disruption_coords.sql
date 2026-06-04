-- Existing DBs: switch conflict key from geometry to explicit lon/lat.

ALTER TABLE odh_export."ogh-disruption"
    ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;

UPDATE odh_export."ogh-disruption"
SET
    lon = ST_X(geometry),
    lat = ST_Y(geometry)
WHERE lon IS NULL OR lat IS NULL;

ALTER TABLE odh_export."ogh-disruption"
    ALTER COLUMN lon SET NOT NULL,
    ALTER COLUMN lat SET NOT NULL;

DROP INDEX IF EXISTS odh_export.ux_ogh_disruption_source_geom;
DROP INDEX IF EXISTS "odh-export".ux_ogh_disruption_source_geom;

CREATE UNIQUE INDEX IF NOT EXISTS ux_ogh_disruption_source_coords
    ON odh_export."ogh-disruption" (source_json, lon, lat);
