-- One-shot: развести дублирующиеся task_number в crm.tasks_area.
-- Keeper: done > wip > free; затем matches_hood; затем севернее; затем key.
-- Остальным — следующий свободный N в том же префиксе М/{okrug}-{YY}-{Q}/{rayon}.
-- Идемпотентно: при отсутствии дублей UPDATE 0.

BEGIN;

WITH hood_hit AS (
    SELECT ta.key
    FROM crm.tasks_area ta
    WHERE ta.geom IS NOT NULL
      AND EXISTS (
          SELECT 1
          FROM odh_export.hood h
          WHERE h.geom IS NOT NULL
            AND ST_Intersects(ta.geom, h.geom)
            AND ST_Within(ST_Centroid(ta.geom), h.geom)
            AND ST_Area(ST_Intersection(ta.geom, h.geom)::geography)
                >= 0.999 * ST_Area(ta.geom::geography)
      )
),
dup_tn AS (
    SELECT task_number
    FROM crm.tasks_area
    WHERE task_number IS NOT NULL
      AND btrim(task_number) <> ''
    GROUP BY task_number
    HAVING COUNT(*) > 1
),
ranked AS (
    SELECT
        ta.key,
        ta.task_number,
        regexp_replace(ta.task_number, '-[0-9]+$', '') AS prefix,
        ROW_NUMBER() OVER (
            PARTITION BY ta.task_number
            ORDER BY
                CASE ta.status
                    WHEN 'done' THEN 0
                    WHEN 'wip'  THEN 1
                    ELSE 2
                END,
                CASE WHEN hh.key IS NOT NULL THEN 0 ELSE 1 END,
                ST_Y(ST_Centroid(ta.geom)) DESC NULLS LAST,
                ta.key
        ) AS keep_rn
    FROM crm.tasks_area ta
    JOIN dup_tn d ON d.task_number = ta.task_number
    LEFT JOIN hood_hit hh ON hh.key = ta.key
),
to_fix AS (
    SELECT
        r.key,
        r.prefix,
        ROW_NUMBER() OVER (
            PARTITION BY r.prefix
            ORDER BY r.keep_rn, r.key
        ) AS seq
    FROM ranked r
    WHERE r.keep_rn > 1
),
kept_nums AS (
    SELECT
        regexp_replace(ta.task_number, '-[0-9]+$', '') AS prefix,
        (regexp_match(ta.task_number, '-([0-9]+)$'))[1]::integer AS n
    FROM crm.tasks_area ta
    WHERE ta.task_number IS NOT NULL
      AND ta.task_number ~ '-[0-9]+$'
      AND NOT EXISTS (SELECT 1 FROM to_fix tf WHERE tf.key = ta.key)
      AND regexp_replace(ta.task_number, '-[0-9]+$', '') IN (
          SELECT DISTINCT prefix FROM to_fix
      )
),
available AS (
    SELECT
        t.prefix,
        g.n,
        ROW_NUMBER() OVER (PARTITION BY t.prefix ORDER BY g.n) AS avail_ord
    FROM (SELECT DISTINCT prefix FROM to_fix) t
    CROSS JOIN LATERAL generate_series(
        1,
        COALESCE(
            (SELECT MAX(k.n) FROM kept_nums k WHERE k.prefix = t.prefix),
            0
        ) + (SELECT COUNT(*) FROM to_fix tf WHERE tf.prefix = t.prefix)
    ) AS g(n)
    WHERE NOT EXISTS (
        SELECT 1 FROM kept_nums k WHERE k.prefix = t.prefix AND k.n = g.n
    )
),
assigned AS (
    SELECT
        tf.key,
        tf.prefix || '-' || a.n AS new_task_number
    FROM to_fix tf
    JOIN available a
      ON a.prefix = tf.prefix
     AND a.avail_ord = tf.seq
)
UPDATE crm.tasks_area ta
SET task_number = a.new_task_number
FROM assigned a
WHERE ta.key = a.key;

COMMIT;
