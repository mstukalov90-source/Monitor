-- M2M API: colleague-submitted photo UUIDs (insert-only, unique per uuid).

CREATE TABLE IF NOT EXISTS genplan.uuid_api (
    id          BIGSERIAL PRIMARY KEY,
    file_name   TEXT NOT NULL,
    uuid        TEXT NOT NULL,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_genplan_uuid_api_uuid_unique
    ON genplan.uuid_api (uuid);

CREATE INDEX IF NOT EXISTS idx_genplan_uuid_api_file_name
    ON genplan.uuid_api (file_name);
CREATE INDEX IF NOT EXISTS idx_genplan_uuid_api_loaded_at
    ON genplan.uuid_api (loaded_at DESC);
