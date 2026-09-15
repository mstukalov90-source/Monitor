-- crm.tasks.source_table: scalar text → text[] (several geometry source tables).
-- Idempotent. Safe to re-run.
--
-- Apply only on SWEB test 77.222.63.161 — do not run on prod 172.21.198.219.

CREATE SCHEMA IF NOT EXISTS crm;

DO $$
DECLARE
    v_ndims integer;
BEGIN
    IF to_regclass('crm.tasks') IS NULL THEN
        RAISE NOTICE 'crm.tasks missing, skip source_table array migration';
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'crm'
          AND table_name = 'tasks'
          AND column_name = 'source_table'
    ) THEN
        RAISE NOTICE 'crm.tasks.source_table missing, skip';
        RETURN;
    END IF;

    SELECT a.attndims
    INTO v_ndims
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'crm'
      AND c.relname = 'tasks'
      AND a.attname = 'source_table'
      AND a.attnum > 0
      AND NOT a.attisdropped;

    IF v_ndims IS NULL THEN
        RAISE NOTICE 'crm.tasks.source_table attr missing, skip';
        RETURN;
    END IF;

    IF v_ndims > 0 THEN
        RAISE NOTICE 'crm.tasks.source_table already array, skip ALTER';
        RETURN;
    END IF;

    DROP TRIGGER IF EXISTS trg_crm_tasks_area_key ON crm.tasks;

    ALTER TABLE crm.tasks
        ALTER COLUMN source_table TYPE text[]
        USING CASE
            WHEN source_table IS NULL THEN NULL
            ELSE ARRAY[source_table]
        END;

    COMMENT ON COLUMN crm.tasks.source_table IS
        'Qualified table names of geometry sources for the task (text[]).';

    IF EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'crm' AND p.proname = 'trg_tasks_refresh_area_key'
    ) THEN
        CREATE TRIGGER trg_crm_tasks_area_key
            AFTER INSERT OR UPDATE OF
                source_table,
                source_row_id,
                photo_uuid,
                photo_lens,
                ogh_id,
                oati_id,
                earthwork_id,
                localwork_id,
                avr_mos_id
            ON crm.tasks
            FOR EACH ROW
            EXECUTE FUNCTION crm.trg_tasks_refresh_area_key();
    END IF;
END $$;

CREATE OR REPLACE FUNCTION crm.iter_task_geom()
RETURNS TABLE(task_key uuid, geom geometry, prio integer)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    split_tbl text;
    split_prio integer;
BEGIN
    FOREACH split_tbl IN ARRAY ARRAY[
        'data_mos.items_2855_polygons',
        'data_mos.items_62501_polygons',
        'data_mos.items_62441_polygons',
        'data_mos.items_62461_polygons',
        'data_mos.items_2855_lines',
        'data_mos.items_62501_lines',
        'data_mos.items_62441_lines',
        'data_mos.items_62461_lines',
        'data_mos.items_2855_points',
        'data_mos.items_62501_points',
        'data_mos.items_62441_points',
        'data_mos.items_62461_points'
    ]
    LOOP
        IF to_regclass(split_tbl) IS NULL THEN
            CONTINUE;
        END IF;
        split_prio := CASE
            WHEN split_tbl LIKE '%_polygons' THEN 2
            WHEN split_tbl LIKE '%_lines' THEN 1
            ELSE 0
        END;
        RETURN QUERY EXECUTE format(
            $q$
            SELECT t.task_key, t.geom, %s::integer
            FROM %s t
            WHERE t.task_key IS NOT NULL
              AND t.geom IS NOT NULL
              AND NOT ST_IsEmpty(t.geom)
            $q$,
            split_prio,
            split_tbl
        );
    END LOOP;

    IF to_regclass('genplan.photo_meta') IS NOT NULL THEN
        RETURN QUERY
        SELECT ct.key, pm.geom, 0
        FROM crm.tasks ct
        JOIN genplan.photo_meta pm
          ON pm.uuid IS NOT NULL
         AND btrim(pm.uuid) <> ''
         AND pm.uuid = ct.photo_uuid
        WHERE ct.photo_uuid IS NOT NULL
          AND pm.geom IS NOT NULL
          AND NOT ST_IsEmpty(pm.geom);

        RETURN QUERY
        SELECT ct.key, pm.geom, 0
        FROM crm.tasks ct
        JOIN genplan.photo_meta pm ON pm.id = ct.source_row_id
        WHERE 'genplan.photo_meta' = ANY(ct.source_table)
          AND ct.source_row_id IS NOT NULL
          AND pm.geom IS NOT NULL
          AND NOT ST_IsEmpty(pm.geom);
    END IF;

    IF to_regclass('lens.reports') IS NOT NULL THEN
        RETURN QUERY
        SELECT ct.key, lr.geom, 0
        FROM crm.tasks ct
        JOIN lens.reports lr
          ON lr.external_report_id IS NOT NULL
         AND btrim(lr.external_report_id::text) <> ''
         AND lr.external_report_id::text = ct.photo_lens
        WHERE ct.photo_lens IS NOT NULL
          AND lr.geom IS NOT NULL
          AND NOT ST_IsEmpty(lr.geom);

        RETURN QUERY
        SELECT ct.key, lr.geom, 0
        FROM crm.tasks ct
        JOIN lens.reports lr ON lr.id = ct.source_row_id
        WHERE 'lens.reports' = ANY(ct.source_table)
          AND ct.source_row_id IS NOT NULL
          AND lr.geom IS NOT NULL
          AND NOT ST_IsEmpty(lr.geom);
    END IF;

    IF to_regclass('odh_export."ogh-disruption"') IS NOT NULL THEN
        RETURN QUERY
        SELECT ct.key, t.geometry, 0
        FROM crm.tasks ct
        JOIN odh_export."ogh-disruption" t
          ON t.id IS NOT NULL
         AND btrim(t.id::text) <> ''
         AND t.id::text = ct.ogh_id
        WHERE ct.ogh_id IS NOT NULL
          AND t.geometry IS NOT NULL
          AND NOT ST_IsEmpty(t.geometry);

        RETURN QUERY
        SELECT ct.key, t.geometry, 0
        FROM crm.tasks ct
        JOIN odh_export."ogh-disruption" t ON t.id = ct.source_row_id
        WHERE 'odh_export.ogh-disruption' = ANY(ct.source_table)
          AND ct.source_row_id IS NOT NULL
          AND t.geometry IS NOT NULL
          AND NOT ST_IsEmpty(t.geometry);
    END IF;

    IF to_regclass('crm.office_task_points') IS NOT NULL THEN
        RETURN QUERY EXECUTE $q$
            SELECT p.task_key, p.point, 0
            FROM crm.office_task_points p
            WHERE p.task_key IS NOT NULL
              AND p.point IS NOT NULL
              AND NOT ST_IsEmpty(p.point)
        $q$;
    END IF;

    IF to_regclass('mggt_field.reports') IS NOT NULL THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'mggt_field' AND table_name = 'reports' AND column_name = 'point'
        ) THEN
            RETURN QUERY EXECUTE $q$
                SELECT r.tasks_key, r.point, 0
                FROM mggt_field.reports r
                WHERE r.tasks_key IS NOT NULL
                  AND r.point IS NOT NULL
                  AND NOT ST_IsEmpty(r.point)
            $q$;
        ELSIF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'mggt_field' AND table_name = 'reports' AND column_name = 'geom'
        ) THEN
            RETURN QUERY EXECUTE $q$
                SELECT r.tasks_key, r.geom, 0
                FROM mggt_field.reports r
                WHERE r.tasks_key IS NOT NULL
                  AND r.geom IS NOT NULL
                  AND NOT ST_IsEmpty(r.geom)
            $q$;
        END IF;
    END IF;
END;
$$;

COMMENT ON FUNCTION crm.iter_task_geom() IS
'Task geometries from data_mos split tables, photo_meta, lens.reports, ogh-disruption, office_task_points, mggt_field.reports.';
