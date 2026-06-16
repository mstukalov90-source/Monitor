-- Genplan photos with disruption=true inside odh_export.hood polygon.
-- Default hood gid=62; change the literal in both queries if needed.
--
-- Verify hood schema before first run:
--   SELECT column_name, udt_name
--   FROM information_schema.columns
--   WHERE table_schema = 'odh_export' AND table_name = 'hood'
--   ORDER BY ordinal_position;
--
--   SELECT gid, ST_GeometryType(geom), ST_IsValid(geom)
--   FROM odh_export.hood
--   WHERE gid = 62;

-- Preview count
SELECT count(*) AS matched
FROM genplan.photo_meta pm
JOIN odh_export.hood h ON h.gid = 62
WHERE pm.disruption IS TRUE
  AND pm.uuid IS NOT NULL
  AND btrim(pm.uuid) <> ''
  AND pm.geom IS NOT NULL
  AND ST_Within(pm.geom, h.geom);

-- List matching photos (uuid for download)
SELECT
    pm.uuid,
    pm.image_name,
    pm.lat,
    pm.lng,
    pm.disruption,
    pm.loaded_at
FROM genplan.photo_meta pm
JOIN odh_export.hood h ON h.gid = 62
WHERE pm.disruption IS TRUE
  AND pm.uuid IS NOT NULL
  AND btrim(pm.uuid) <> ''
  AND pm.geom IS NOT NULL
  AND ST_Within(pm.geom, h.geom)
ORDER BY pm.loaded_at DESC;
