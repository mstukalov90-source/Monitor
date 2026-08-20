-- Fivegen / DIT AI detections (one-shot JSON dumps → dit_detect.ai_results).

CREATE SCHEMA IF NOT EXISTS dit_detect;

CREATE TABLE IF NOT EXISTS dit_detect.ai_results (
    result_id               UUID PRIMARY KEY,
    origin_screenshot_id    UUID,
    device                  UUID,
    camera                  UUID,
    create_timestamp        BIGINT,
    created_at              TIMESTAMPTZ,
    image                   TEXT,
    image_type              INTEGER,
    issues                  JSONB NOT NULL DEFAULT '[]'::jsonb,
    latitude                DOUBLE PRECISION,
    longitude               DOUBLE PRECISION,
    geom                    GEOMETRY(Point, 4326),
    angle                   INTEGER,
    speed                   DOUBLE PRECISION,
    valid                   BOOLEAN,
    height                  DOUBLE PRECISION,
    ptz_position            JSONB,
    source_file             TEXT NOT NULL,
    provider                TEXT,
    loaded_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dit_detect_ai_results_geom
    ON dit_detect.ai_results USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_dit_detect_ai_results_camera
    ON dit_detect.ai_results (camera);

CREATE INDEX IF NOT EXISTS idx_dit_detect_ai_results_created_at
    ON dit_detect.ai_results (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dit_detect_ai_results_source_file
    ON dit_detect.ai_results (source_file);
