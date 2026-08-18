-- Link CRM tasks to crm.tasks_area.key when task geometry intersects an area polygon.
-- Idempotent. Safe to re-run.
--
-- Backfill:
--   SET statement_timeout = '30min';
--   CALL crm.refresh_task_area_keys();
--
-- Smoke:
--   SELECT count(*) FILTER (WHERE area_key IS NOT NULL) AS with_area,
--          count(*) FILTER (WHERE area_key IS NULL) AS without_area
--   FROM crm.tasks;
--
--   SELECT key, cardinality(area_key) AS n
--   FROM crm.tasks
--   WHERE cardinality(area_key) > 1
--   LIMIT 20;

CREATE SCHEMA IF NOT EXISTS crm;

-- ---------------------------------------------------------------------------
-- Columns + GIN
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'tasks',
        'tasks_field',
        'tasks_clear',
        'tasks_delay',
        'tasks_done_legal',
        'tasks_done_illegal'
    ]
    LOOP
        IF to_regclass(format('crm.%I', tbl)) IS NULL THEN
            CONTINUE;
        END IF;
        EXECUTE format(
            'ALTER TABLE crm.%I ADD COLUMN IF NOT EXISTS area_key UUID[]',
            tbl
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS idx_crm_%s_area_key ON crm.%I USING GIN (area_key) WHERE area_key IS NOT NULL',
            tbl,
            tbl
        );
        EXECUTE format(
            'COMMENT ON COLUMN crm.%I.area_key IS %L',
            tbl,
            'crm.tasks_area.key values whose polygons intersect the task geometry'
        );
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Geometry iterator + view (polygon > line > point)
-- ---------------------------------------------------------------------------

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
'Task geometries from data_mos split tables, photo_meta, lens.reports, office_task_points, mggt_field.reports.';

CREATE OR REPLACE VIEW crm.v_task_geom AS
SELECT DISTINCT ON (g.task_key)
    g.task_key,
    g.geom
FROM crm.iter_task_geom() g
ORDER BY g.task_key, g.prio DESC;

COMMENT ON VIEW crm.v_task_geom IS
'One geometry per crm.tasks.key (polygon over line over point).';

-- ---------------------------------------------------------------------------
-- Area keys from intersection
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION crm.task_area_keys(p_geom geometry)
RETURNS uuid[]
LANGUAGE sql
STABLE
AS $$
    SELECT CASE
        WHEN p_geom IS NULL OR ST_IsEmpty(p_geom) THEN NULL
        ELSE (
            SELECT NULLIF(array_agg(DISTINCT a.key ORDER BY a.key), ARRAY[]::uuid[])
            FROM crm.tasks_area a
            WHERE a.geom IS NOT NULL
              AND NOT ST_IsEmpty(a.geom)
              AND ST_Intersects(ST_MakeValid(p_geom), a.geom)
        )
    END;
$$;

COMMENT ON FUNCTION crm.task_area_keys(geometry) IS
'crm.tasks_area.key values whose polygons intersect p_geom (ST_Intersects + ST_MakeValid on the task geom).';

CREATE OR REPLACE FUNCTION crm.task_area_keys_for_task(p_task_key uuid)
RETURNS uuid[]
LANGUAGE sql
STABLE
AS $$
    SELECT crm.task_area_keys(g.geom)
    FROM crm.v_task_geom g
    WHERE g.task_key = p_task_key
$$;

-- ---------------------------------------------------------------------------
-- Full refresh (backfill + after area edits)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE PROCEDURE crm.refresh_task_area_keys()
LANGUAGE plpgsql
AS $$
DECLARE
    snap text;
    v_updated integer := 0;
BEGIN
    UPDATE crm.tasks t
    SET area_key = s.keys
    FROM (
        SELECT g.task_key,
               NULLIF(array_agg(DISTINCT a.key ORDER BY a.key), ARRAY[]::uuid[]) AS keys
        FROM crm.v_task_geom g
        LEFT JOIN crm.tasks_area a
          ON a.geom IS NOT NULL
         AND NOT ST_IsEmpty(a.geom)
         AND ST_Intersects(ST_MakeValid(g.geom), a.geom)
        GROUP BY g.task_key
    ) s
    WHERE t.key = s.task_key
      AND t.area_key IS DISTINCT FROM s.keys;
    GET DIAGNOSTICS v_updated = ROW_COUNT;

    UPDATE crm.tasks t
    SET area_key = NULL
    WHERE t.area_key IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM crm.v_task_geom g WHERE g.task_key = t.key
      );

    FOREACH snap IN ARRAY ARRAY[
        'tasks_field',
        'tasks_clear',
        'tasks_delay',
        'tasks_done_legal',
        'tasks_done_illegal'
    ]
    LOOP
        IF to_regclass(format('crm.%I', snap)) IS NULL THEN
            CONTINUE;
        END IF;
        EXECUTE format(
            $q$
            UPDATE crm.%I s
            SET area_key = t.area_key
            FROM crm.tasks t
            WHERE s.task_key = t.key
              AND s.area_key IS DISTINCT FROM t.area_key
            $q$,
            snap
        );
        EXECUTE format(
            $q$
            UPDATE crm.%I s
            SET area_key = x.keys
            FROM (
                SELECT g.task_key,
                       NULLIF(array_agg(DISTINCT a.key ORDER BY a.key), ARRAY[]::uuid[]) AS keys
                FROM crm.v_task_geom g
                LEFT JOIN crm.tasks_area a
                  ON a.geom IS NOT NULL
                 AND NOT ST_IsEmpty(a.geom)
                 AND ST_Intersects(ST_MakeValid(g.geom), a.geom)
                GROUP BY g.task_key
            ) x
            WHERE s.task_key = x.task_key
              AND s.area_key IS NULL
            $q$,
            snap
        );
    END LOOP;

    RAISE NOTICE 'refresh_task_area_keys: crm.tasks matched updates=%', v_updated;
END;
$$;

COMMENT ON PROCEDURE crm.refresh_task_area_keys() IS
'Recompute area_key on crm.tasks and snapshot tables from current geometry ∩ tasks_area.';

-- ---------------------------------------------------------------------------
-- Triggers: crm.tasks
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION crm.trg_tasks_refresh_area_key()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_keys uuid[];
BEGIN
    v_keys := crm.task_area_keys_for_task(NEW.key);
    IF NEW.area_key IS DISTINCT FROM v_keys THEN
        UPDATE crm.tasks
        SET area_key = v_keys
        WHERE key = NEW.key
          AND area_key IS DISTINCT FROM v_keys;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_crm_tasks_area_key ON crm.tasks;
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

-- ---------------------------------------------------------------------------
-- Triggers: data_mos split task_key / geom
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION crm.trg_split_refresh_task_area_key()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_key uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_key := OLD.task_key;
    ELSE
        v_key := NEW.task_key;
    END IF;
    IF v_key IS NOT NULL THEN
        UPDATE crm.tasks
        SET area_key = crm.task_area_keys_for_task(v_key)
        WHERE key = v_key;
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.task_key IS NOT NULL
       AND NEW.task_key IS DISTINCT FROM OLD.task_key
    THEN
        UPDATE crm.tasks
        SET area_key = crm.task_area_keys_for_task(OLD.task_key)
        WHERE key = OLD.task_key;
    END IF;
    RETURN NULL;
END;
$$;

DO $$
DECLARE
    split_tbl text;
    trg_name text;
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
        trg_name := 'trg_crm_area_key_' || replace(split_tbl, '.', '_');
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %s', trg_name, split_tbl);
        EXECUTE format(
            $q$
            CREATE TRIGGER %I
                AFTER INSERT OR UPDATE OF task_key, geom OR DELETE
                ON %s
                FOR EACH ROW
                EXECUTE FUNCTION crm.trg_split_refresh_task_area_key()
            $q$,
            trg_name,
            split_tbl
        );
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Triggers: tasks_area geom changes → full refresh
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION crm.trg_tasks_area_refresh_area_keys()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    CALL crm.refresh_task_area_keys();
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_crm_tasks_area_refresh_area_keys ON crm.tasks_area;
CREATE TRIGGER trg_crm_tasks_area_refresh_area_keys
    AFTER INSERT OR UPDATE OF geom OR DELETE
    ON crm.tasks_area
    FOR EACH STATEMENT
    EXECUTE FUNCTION crm.trg_tasks_area_refresh_area_keys();

-- ---------------------------------------------------------------------------
-- Triggers: snapshot BEFORE INSERT copy from parent
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION crm.trg_snapshot_copy_area_key()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.area_key IS NULL AND NEW.task_key IS NOT NULL THEN
        SELECT t.area_key INTO NEW.area_key
        FROM crm.tasks t
        WHERE t.key = NEW.task_key;
    END IF;
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    snap text;
    trg_name text;
BEGIN
    FOREACH snap IN ARRAY ARRAY[
        'tasks_field',
        'tasks_clear',
        'tasks_delay',
        'tasks_done_legal',
        'tasks_done_illegal'
    ]
    LOOP
        IF to_regclass(format('crm.%I', snap)) IS NULL THEN
            CONTINUE;
        END IF;
        trg_name := 'trg_crm_' || snap || '_copy_area_key';
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON crm.%I', trg_name, snap);
        EXECUTE format(
            $q$
            CREATE TRIGGER %I
                BEFORE INSERT ON crm.%I
                FOR EACH ROW
                EXECUTE FUNCTION crm.trg_snapshot_copy_area_key()
            $q$,
            trg_name,
            snap
        );
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Optional: office points
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF to_regclass('crm.office_task_points') IS NULL THEN
        RETURN;
    END IF;
    DROP TRIGGER IF EXISTS trg_crm_office_points_area_key ON crm.office_task_points;
    CREATE TRIGGER trg_crm_office_points_area_key
        AFTER INSERT OR UPDATE OF point, task_key OR DELETE
        ON crm.office_task_points
        FOR EACH ROW
        EXECUTE FUNCTION crm.trg_split_refresh_task_area_key();
END $$;
