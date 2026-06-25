-- Квартальная нумерация crm.tasks_area по родительским полигонам odh_export.hood.
-- Безопасно запускать повторно (CREATE OR REPLACE, ADD COLUMN IF NOT EXISTS).
--
-- Формат task_number:
--   М/{okrug_shor}-{YY}-{Q}/{rayon_нормализованный}-{N}
-- Пример: М/ЦАО-26-2/Тверской-1
--
-- N — порядковый номер внутри одного hood (gid), с севера на юг:
--   ORDER BY ST_Y(ST_Centroid(geom)) DESC, key
--
-- Перед первым запуском проверьте схему hood:
--   SELECT column_name, udt_name
--   FROM information_schema.columns
--   WHERE table_schema = 'odh_export' AND table_name = 'hood'
--   ORDER BY ordinal_position;
--
-- Ручной запуск:
--   CALL crm.refresh_tasks_area_quarterly();

CREATE SCHEMA IF NOT EXISTS crm;

-- Колонка для квартального номера задачи.
ALTER TABLE crm.tasks_area
    ADD COLUMN IF NOT EXISTS task_number TEXT;

CREATE INDEX IF NOT EXISTS idx_crm_tasks_area_task_number
    ON crm.tasks_area (task_number);

CREATE OR REPLACE PROCEDURE crm.refresh_tasks_area_quarterly()
LANGUAGE plpgsql
AS $$
DECLARE
    v_run_date        date;
    v_yy              text;
    v_quarter         integer;
    v_updated         integer := 0;
    v_unmatched       integer := 0;
    v_unmatched_keys  text;
BEGIN
    -- Дата, год и квартал — по московскому времени.
    v_run_date := (timezone('Europe/Moscow', now()))::date;
    v_yy       := to_char(v_run_date, 'YY');
    v_quarter  := extract(quarter FROM v_run_date)::integer;

    -- Шаг 1: пространственный join tasks_area → hood.
    -- ST_Within слишком строгий: у соседних полигонов бывает микровыступ за границу hood
    -- (доли м² при 100% визуальном попадании). Критерий: центроид внутри hood и
    -- не менее 99.9% площади дочернего полигона лежит в hood.
    -- Шаг 2: ROW_NUMBER() внутри каждого hood по Y центроида (север → юг).
    -- Шаг 3: сборка task_number и площади в кв. м (округление до 0.0).
    -- Шаг 4: массовое обновление task_number и area (geom не трогаем).
    WITH matched AS (
        SELECT
            ta.key,
            h.gid AS hood_gid,
            coalesce(h.okrug_shor, h.okrug) AS okrug_shor,
            h.rayon,
            ta.geom,
            ST_Y(ST_Centroid(ta.geom)) AS centroid_y,
            round(ST_Area(ta.geom::geography)::numeric, 1)::double precision AS area_sqm
        FROM crm.tasks_area ta
        JOIN LATERAL (
            SELECT h_inner.*
            FROM odh_export.hood h_inner
            WHERE h_inner.geom IS NOT NULL
              AND ST_Intersects(ta.geom, h_inner.geom)
              AND ST_Within(ST_Centroid(ta.geom), h_inner.geom)
              AND ST_Area(ST_Intersection(ta.geom, h_inner.geom)::geography)
                  >= 0.999 * ST_Area(ta.geom::geography)
            -- При пересечении границ нескольких hood — берём максимальное пересечение.
            ORDER BY ST_Area(ST_Intersection(ta.geom, h_inner.geom)::geography) DESC
            LIMIT 1
        ) h ON true
        WHERE ta.geom IS NOT NULL
    ),
    numbered AS (
        SELECT
            m.key,
            m.hood_gid,
            m.okrug_shor,
            m.rayon,
            m.area_sqm,
            ROW_NUMBER() OVER (
                PARTITION BY m.hood_gid
                ORDER BY m.centroid_y DESC, m.key
            ) AS n
        FROM matched m
    ),
    formatted AS (
        SELECT
            n.key,
            n.area_sqm,
            format(
                'М/%s-%s-%s/%s-%s',
                n.okrug_shor,
                v_yy,
                v_quarter,
                regexp_replace(n.rayon, '[ -]+', '_', 'g'),
                n.n
            ) AS task_number
        FROM numbered n
    )
    UPDATE crm.tasks_area ta
    SET
        task_number = f.task_number,
        area        = f.area_sqm
    FROM formatted f
    WHERE ta.key = f.key;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    -- Полигоны без родительского hood: не обновляем, пишем WARNING.
    SELECT count(*)
    INTO v_unmatched
    FROM crm.tasks_area ta
    WHERE ta.geom IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM odh_export.hood h
          WHERE h.geom IS NOT NULL
            AND ST_Intersects(ta.geom, h.geom)
            AND ST_Within(ST_Centroid(ta.geom), h.geom)
            AND ST_Area(ST_Intersection(ta.geom, h.geom)::geography)
                >= 0.999 * ST_Area(ta.geom::geography)
      );

    RAISE NOTICE 'refresh_tasks_area_quarterly: дата=%, квартал=%, год=20%, обновлено % строк',
        v_run_date, v_quarter, v_yy, v_updated;

    IF v_unmatched > 0 THEN
        SELECT string_agg(sub.key::text, ', ' ORDER BY sub.key)
        INTO v_unmatched_keys
        FROM (
            SELECT ta.key
            FROM crm.tasks_area ta
            WHERE ta.geom IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM odh_export.hood h
                  WHERE h.geom IS NOT NULL
                    AND ST_Intersects(ta.geom, h.geom)
                    AND ST_Within(ST_Centroid(ta.geom), h.geom)
                    AND ST_Area(ST_Intersection(ta.geom, h.geom)::geography)
                        >= 0.999 * ST_Area(ta.geom::geography)
              )
            ORDER BY ta.key
            LIMIT 20
        ) sub;

        RAISE WARNING 'refresh_tasks_area_quarterly: % полигон(ов) не попали ни в один hood (task_number не изменён). key (первые 20): %',
            v_unmatched, v_unmatched_keys;
    END IF;
END;
$$;

COMMENT ON PROCEDURE crm.refresh_tasks_area_quarterly() IS
'Квартальная нумерация crm.tasks_area: пространственный join с odh_export.hood
(центроид внутри hood, >=99.9% площади внутри), task_number (М/{okrug_shor}-{YY}-{Q}/{rayon}-{N}),
площадь в кв. м с округлением до 0.0. N сбрасывается для каждого hood,
сортировка с севера на юг по ST_Y(ST_Centroid(geom)).';

-- ---------------------------------------------------------------------------
-- Опционально: автозапуск в первый день каждого квартала через pg_cron.
-- Требует расширение pg_cron и настройку cron.timezone = ''Europe/Moscow''.
--
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
--
-- SELECT cron.schedule(
--     'crm-tasks-area-quarterly',
--     '0 0 1 1,4,7,10 *',
--     $$CALL crm.refresh_tasks_area_quarterly()$$
-- );
--
-- Удаление задания:
--   SELECT cron.unschedule('crm-tasks-area-quarterly');
