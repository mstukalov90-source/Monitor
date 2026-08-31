-- Incremental log for genplan photo confirm API (PATCH /api/photos/{uuid}/confirm).
-- Idempotent. Safe to re-run.

CREATE SCHEMA IF NOT EXISTS genplan;

CREATE TABLE IF NOT EXISTS genplan.photo_confirm_log (
    photo_uuid      TEXT PRIMARY KEY,
    confirm         BOOLEAN NOT NULL,
    status          TEXT NOT NULL,
    http_status     INTEGER,
    error_message   TEXT,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genplan_photo_confirm_log_status
    ON genplan.photo_confirm_log (status);

CREATE INDEX IF NOT EXISTS idx_genplan_photo_confirm_log_confirm
    ON genplan.photo_confirm_log (confirm);

CREATE INDEX IF NOT EXISTS idx_genplan_photo_confirm_log_sent_at
    ON genplan.photo_confirm_log (sent_at DESC);

COMMENT ON TABLE genplan.photo_confirm_log IS
    'Last confirm sent to MSI Holes for a genplan photo uuid';
COMMENT ON COLUMN genplan.photo_confirm_log.status IS
    'sent | error | skipped_cam';
