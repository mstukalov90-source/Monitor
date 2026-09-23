-- odh_export.ogh_analiz: OrderName must not be unique.
-- The source (mggt_asu gis.ogh_analiz) re-issues OrderName under new ids, which
-- breaks the id-based upsert in ogh_analiz_sync (duplicate key on
-- ux_ogh_analiz_ordername). Equality lookups (ozn_excel_inbox, sql/37 backfill)
-- only need a plain index.
-- Idempotent. Safe to re-run.

DROP INDEX IF EXISTS odh_export.ux_ogh_analiz_ordername;

CREATE INDEX IF NOT EXISTS ix_ogh_analiz_ordername
    ON odh_export.ogh_analiz ("OrderName");
