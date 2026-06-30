-- Genplan photos with disruption=true inside odh_export.hood polygons.
-- Default hood gids: 20, 62, 69-82, 122, 124.
--
-- Verify hood schema before first run:
--   SELECT column_name, udt_name
--   FROM information_schema.columns
--   WHERE table_schema = 'odh_export' AND table_name = 'hood'
--   ORDER BY ordinal_position;
--
--   SELECT gid, rayon, okrug, ST_GeometryType(geom) AS gtype, ST_IsValid(geom) AS valid
--   FROM odh_export.hood
--   WHERE gid IN (20, 62, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 122, 124)
--   ORDER BY gid;

-- Preview count
SELECT count(*) AS matched
FROM genplan.photo_meta pm
WHERE pm.disruption IS TRUE
  AND pm.uuid IS NOT NULL
  AND btrim(pm.uuid) <> ''
  AND pm.geom IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM odh_export.hood h
    WHERE h.gid IN (20, 62, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 122, 124)
      AND ST_Within(pm.geom, h.geom)
  );

-- List matching photos (uuid for download)
SELECT
    pm.uuid,
    pm.image_name,
    pm.lat,
    pm.lng,
    pm.disruption,
    pm.loaded_at
FROM genplan.photo_meta pm
WHERE pm.disruption IS TRUE
  AND pm.uuid IS NOT NULL
  AND btrim(pm.uuid) <> ''
  AND pm.geom IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM odh_export.hood h
    WHERE h.gid IN (20, 62, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 122, 124)
      AND ST_Within(pm.geom, h.geom)
  )
ORDER BY pm.loaded_at DESC;
