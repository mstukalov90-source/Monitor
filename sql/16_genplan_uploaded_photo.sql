-- Outbound MSI Holes photo uploads (genplan_upload job).

CREATE TABLE IF NOT EXISTS genplan.uploaded_photo (
    id          BIGSERIAL PRIMARY KEY,
    file_name   TEXT NOT NULL,
    geom        GEOMETRY(Point, 4326),
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genplan_uploaded_photo_geom
    ON genplan.uploaded_photo USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_genplan_uploaded_photo_file_name
    ON genplan.uploaded_photo (file_name);
CREATE INDEX IF NOT EXISTS idx_genplan_uploaded_photo_loaded_at
    ON genplan.uploaded_photo (loaded_at DESC);

ALTER TABLE genplan.uploaded_photo ADD COLUMN IF NOT EXISTS uuid TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_genplan_uploaded_photo_uuid_unique
    ON genplan.uploaded_photo (uuid)
    WHERE uuid IS NOT NULL AND btrim(uuid) <> '';
