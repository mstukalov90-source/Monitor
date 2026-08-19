-- Incremental log for situation photos uploaded to MSI Holes (genplan API).
-- public.mview_mon_op_prod / mview_mon_op_files and the situation share stay read-only.

CREATE SCHEMA IF NOT EXISTS genplan;

CREATE TABLE IF NOT EXISTS genplan.situation_photo_log (
    id              bigserial PRIMARY KEY,
    source_oid      numeric,
    ono             text,
    source_fnm      text,
    source_relpath  text NOT NULL,
    status          text NOT NULL,
    genplan_uuid    text,
    error_message   text,
    processed_at    timestamptz NOT NULL DEFAULT NOW(),
    UNIQUE (source_relpath)
);

CREATE INDEX IF NOT EXISTS idx_situation_photo_log_status
    ON genplan.situation_photo_log (status);

CREATE INDEX IF NOT EXISTS idx_situation_photo_log_oid
    ON genplan.situation_photo_log (source_oid);

CREATE INDEX IF NOT EXISTS idx_situation_photo_log_processed_at
    ON genplan.situation_photo_log (processed_at DESC);
