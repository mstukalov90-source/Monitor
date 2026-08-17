-- Квартальная нумерация crm.tasks_area по родительским полигонам odh_export.hood.
-- Без совпадения с hood — атрибуты из tasks_area.
-- Единый N на (okrug_shor, rayon) для всех статусов — без дублей hood vs fallback.
-- Безопасно запускать повторно (CREATE OR REPLACE, ADD COLUMN IF NOT EXISTS).
--
-- Формат task_number:
--   М/{okrug_shor}-{YY}-{Q}/{rayon_нормализованный}-{N}
-- Пример: М/ЦАО-26-2/Тверской-1
--
-- N — порядковый номер внутри normalize(okrug_shor)+normalize(rayon),
-- с севера на юг: ORDER BY ST_Y(ST_Centroid(geom)) DESC, key
--
-- Ручной запуск:
--   CALL crm.refresh_tasks_area_quarterly();

CREATE SCHEMA IF NOT EXISTS crm;

ALTER TABLE crm.tasks_area
    ADD COLUMN IF NOT EXISTS task_number TEXT;

CREATE INDEX IF NOT EXISTS idx_crm_tasks_area_task_number
    ON crm.tasks_area (task_number);

CREATE OR REPLACE FUNCTION crm.normalize_attr_text(p_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT CASE
        WHEN btrim(v) = '' THEN NULL
        ELSE btrim(v)
    END
    FROM (
        SELECT regexp_replace(
                   regexp_replace(
                       regexp_replace(p_value, E'[\r\n]+', ' ', 'g'),
                       E'\\s+', ' ', 'g'
                   ),
                   E'\\s*-\\s*', '-', 'g'
               ) AS v
    ) s;
$$;

COMMENT ON FUNCTION crm.normalize_attr_text(text) IS
'Чистит текстовые атрибуты tasks_area: CR/LF → пробел, схлопывание пробелов, пробелы вокруг дефиса.';

CREATE OR REPLACE FUNCTION crm.normalize_task_label(p_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN a IS NULL OR a = '' THEN NULL
        ELSE btrim(
            regexp_replace(
                regexp_replace(a, '[ -]+', '_', 'g'),
                '_+', '_', 'g'
            ),
            '_'
        )
    END
    FROM (SELECT crm.normalize_attr_text(p_value) AS a) s;
$$;

COMMENT ON FUNCTION crm.normalize_task_label(text) IS
'Лейбл для task_number: normalize_attr_text + замена пробелов/дефисов на _, без краевых _.';

CREATE OR REPLACE PROCEDURE crm.refresh_tasks_area_quarterly()
LANGUAGE plpgsql
AS $$
DECLARE
    v_run_date      date;
    v_yy            text;
    v_quarter       integer;
    v_updated       integer := 0;
    v_still_missing integer := 0;
    v_missing_keys  text;
BEGIN
    v_run_date := (timezone('Europe/Moscow', now()))::date;
    v_yy       := to_char(v_run_date, 'YY');
    v_quarter  := extract(quarter FROM v_run_date)::integer;

    -- Атрибуция: hood при match, иначе столбцы tasks_area.
    -- Один ROW_NUMBER на (okrug_label, rayon_label) — без раздельных счётчиков.
    -- Двухфазный UPDATE: сначала NULL (чтобы не бить unique index), потом финальные номера.
    DROP TABLE IF EXISTS _crm_tasks_area_numbered;
    CREATE TEMP TABLE _crm_tasks_area_numbered ON COMMIT DROP AS
    WITH attributed AS (
        SELECT
            ta.key,
            coalesce(
                nullif(btrim(h.okrug_shor), ''),
                nullif(btrim(h.okrug), ''),
                nullif(btrim(ta.okrug_shor), ''),
                nullif(btrim(ta.okrug), '')
            ) AS okrug_shor,
            coalesce(
                nullif(btrim(h.rayon), ''),
                nullif(btrim(ta.rayon), '')
            ) AS rayon,
            ST_Y(ST_Centroid(ta.geom)) AS centroid_y,
            round(ST_Area(ta.geom::geography)::numeric, 1)::double precision AS area_sqm
        FROM crm.tasks_area ta
        LEFT JOIN LATERAL (
            SELECT h_inner.okrug_shor, h_inner.okrug, h_inner.rayon
            FROM odh_export.hood h_inner
            WHERE h_inner.geom IS NOT NULL
              AND ST_Intersects(ta.geom, h_inner.geom)
              AND ST_Within(ST_Centroid(ta.geom), h_inner.geom)
              AND ST_Area(ST_Intersection(ta.geom, h_inner.geom)::geography)
                  >= 0.999 * ST_Area(ta.geom::geography)
            ORDER BY ST_Area(ST_Intersection(ta.geom, h_inner.geom)::geography) DESC
            LIMIT 1
        ) h ON true
        WHERE ta.geom IS NOT NULL
    ),
    labeled AS (
        SELECT
            a.key,
            a.area_sqm,
            a.centroid_y,
            crm.normalize_task_label(a.okrug_shor) AS okrug_label,
            crm.normalize_task_label(a.rayon) AS rayon_label
        FROM attributed a
        WHERE crm.normalize_task_label(a.okrug_shor) IS NOT NULL
          AND crm.normalize_task_label(a.rayon) IS NOT NULL
    ),
    numbered AS (
        SELECT
            l.key,
            l.area_sqm,
            l.okrug_label,
            l.rayon_label,
            ROW_NUMBER() OVER (
                PARTITION BY l.okrug_label, l.rayon_label
                ORDER BY l.centroid_y DESC, l.key
            ) AS n
        FROM labeled l
    )
    SELECT
        n.key,
        n.area_sqm,
        format(
            'М/%s-%s-%s/%s-%s',
            n.okrug_label,
            v_yy,
            v_quarter,
            n.rayon_label,
            n.n
        ) AS task_number
    FROM numbered n;

    UPDATE crm.tasks_area ta
    SET
        task_number = NULL,
        area        = n.area_sqm
    FROM _crm_tasks_area_numbered n
    WHERE ta.key = n.key;

    UPDATE crm.tasks_area ta
    SET task_number = n.task_number
    FROM _crm_tasks_area_numbered n
    WHERE ta.key = n.key;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    SELECT count(*)
    INTO v_still_missing
    FROM crm.tasks_area ta
    WHERE ta.geom IS NOT NULL
      AND (ta.task_number IS NULL OR btrim(ta.task_number) = '');

    RAISE NOTICE
        'refresh_tasks_area_quarterly: дата=%, квартал=%, год=20%, обновлено=%',
        v_run_date, v_quarter, v_yy, v_updated;

    IF v_still_missing > 0 THEN
        SELECT string_agg(sub.key::text, ', ' ORDER BY sub.key)
        INTO v_missing_keys
        FROM (
            SELECT ta.key
            FROM crm.tasks_area ta
            WHERE ta.geom IS NOT NULL
              AND (ta.task_number IS NULL OR btrim(ta.task_number) = '')
            ORDER BY ta.key
            LIMIT 20
        ) sub;

        RAISE WARNING
            'refresh_tasks_area_quarterly: % полигон(ов) без task_number (нет okrug_shor/rayon). key (первые 20): %',
            v_still_missing, v_missing_keys;
    END IF;
END;
$$;

COMMENT ON PROCEDURE crm.refresh_tasks_area_quarterly() IS
'Квартальная нумерация crm.tasks_area: атрибуты из odh_export.hood при match,
иначе из tasks_area. Единый N на (okrug_shor, rayon) для всех статусов
(М/{okrug}-{YY}-{Q}/{rayon}-{N} через normalize_task_label). Площадь в кв. м до 0.0.
N с севера на юг по ST_Y(ST_Centroid(geom)).';

-- Unique index создаётся отдельно после устранения дублей:
--   CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_tasks_area_task_number
--       ON crm.tasks_area (task_number) WHERE task_number IS NOT NULL;