-- Stable uuid column for genplan.photo_meta upserts (M2M API + dedup).

ALTER TABLE genplan.photo_meta ADD COLUMN IF NOT EXISTS uuid TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_genplan_photo_meta_uuid_unique
    ON genplan.photo_meta (uuid)
    WHERE uuid IS NOT NULL AND btrim(uuid) <> '';
