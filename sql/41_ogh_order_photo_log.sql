-- Incremental log for OGH order photos uploaded to MSI Holes (genplan API).
-- public.mview_mon_op_prod and the Заказы share stay read-only.

CREATE SCHEMA IF NOT EXISTS genplan;

CREATE TABLE IF NOT EXISTS genplan.ogh_order_photo_log (
    id              bigserial PRIMARY KEY,
    source_oid      numeric,
    ogno            text,
    source_url      text,
    source_relpath  text NOT NULL,
    status          text NOT NULL,
    genplan_uuid    text,
    error_message   text,
    processed_at    timestamptz NOT NULL DEFAULT NOW(),
    UNIQUE (source_relpath)
);

CREATE INDEX IF NOT EXISTS idx_ogh_order_photo_log_status
    ON genplan.ogh_order_photo_log (status);

CREATE INDEX IF NOT EXISTS idx_ogh_order_photo_log_oid
    ON genplan.ogh_order_photo_log (source_oid);

CREATE INDEX IF NOT EXISTS idx_ogh_order_photo_log_processed_at
    ON genplan.ogh_order_photo_log (processed_at DESC);
