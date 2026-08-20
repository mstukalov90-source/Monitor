-- Watermark for topopassport.topotext → odh_export."ogh-disruption".
-- GeoJSON-loaded rows keep source_fid NULL.

ALTER TABLE odh_export."ogh-disruption"
    ADD COLUMN IF NOT EXISTS source_fid BIGINT;

CREATE INDEX IF NOT EXISTS idx_ogh_disruption_source_fid
    ON odh_export."ogh-disruption" (source_fid);
