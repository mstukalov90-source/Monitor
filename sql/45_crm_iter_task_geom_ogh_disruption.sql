-- Include odh_export."ogh-disruption" in crm.iter_task_geom() so
-- crm.refresh_task_area_keys() can set area_key for OGH disruption tasks.
-- Idempotent. Safe to re-run.

CREATE SCHEMA IF NOT EXISTS crm;

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
        WHERE ct.source_table = 'genplan.photo_meta'
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
        WHERE ct.source_table = 'lens.reports'
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
        WHERE ct.source_table = 'odh_export.ogh-disruption'
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
