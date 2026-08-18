-- Log of Excel inbox uploads that fill odh_export.ogh_analiz.ozn_date / executor.

CREATE SCHEMA IF NOT EXISTS odh_export;

CREATE TABLE IF NOT EXISTS odh_export.ozn_upload_log (
    id                  bigserial PRIMARY KEY,
    processed_at        timestamptz NOT NULL DEFAULT NOW(),
    file_name           text NOT NULL,
    file_sha256         text,
    file_size_bytes     bigint,
    status              text NOT NULL,
    excel_rows          integer NOT NULL DEFAULT 0,
    filled_ordername    integer NOT NULL DEFAULT 0,
    filled_order        integer NOT NULL DEFAULT 0,
    missing_count       integer NOT NULL DEFAULT 0,
    skipped_rows        integer NOT NULL DEFAULT 0,
    missing_orders      text[],
    error_message       text,
    duration_ms         integer
);

CREATE INDEX IF NOT EXISTS idx_ozn_upload_log_processed_at
    ON odh_export.ozn_upload_log (processed_at DESC);

CREATE INDEX IF NOT EXISTS idx_ozn_upload_log_file_name
    ON odh_export.ozn_upload_log (file_name);
