-- One-time (.161 test): return Solntsevo district tasks to WebCRM "active".
-- Active = row stays in crm.tasks, snapshot rows are deleted.
-- Does NOT touch crm.tasks, crm.tasks_area, *_log, items_*.task_key.
--
-- Dry-run (default):
--   psql -v ON_ERROR_STOP=1 -f sql/one_time/solntsevo_return_to_active.sql
-- Apply:
--   psql -v ON_ERROR_STOP=1 -v apply=1 -f sql/one_time/solntsevo_return_to_active.sql

\if :{?apply}
\else
\set apply 0
\endif

\echo === solntsevo_return_to_active apply=:apply ===

BEGIN;

CREATE TEMP TABLE solntsevo_hood (
    gid integer PRIMARY KEY,
    rayon text,
    geom geometry
);

CREATE TEMP TABLE solntsevo_keys (
    task_key uuid PRIMARY KEY
);

CREATE TEMP TABLE solntsevo_report (
    step text NOT NULL,
    snapshot text NOT NULL,
    n bigint NOT NULL
);

CREATE TEMP TABLE solntsevo_snapshots (
    tbl text PRIMARY KEY
);

DO $$
DECLARE
    v_hood_n integer;
    v_gid integer;
    v_rayon text;
    v_tasks_before bigint;
    v_keys bigint;
    snap text;
    has_rayon boolean;
    n_before bigint;
    n_deleted bigint;
    n_after bigint;
    n_tasks_after bigint;
BEGIN
    SELECT count(*) INTO v_hood_n
    FROM odh_export.hood
    WHERE rayon ILIKE '%солнцев%';

    IF v_hood_n <> 1 THEN
        RAISE EXCEPTION
            'expected exactly 1 odh_export.hood row with rayon ILIKE %%солнцев%%, got %',
            v_hood_n;
    END IF;

    INSERT INTO solntsevo_hood (gid, rayon, geom)
    SELECT h.gid, h.rayon, h.geom
    FROM odh_export.hood h
    WHERE h.rayon ILIKE '%солнцев%';

    SELECT gid, rayon INTO v_gid, v_rayon FROM solntsevo_hood;
    RAISE NOTICE 'hood gid=% rayon=%', v_gid, v_rayon;

    INSERT INTO solntsevo_snapshots (tbl)
    SELECT t.table_name
    FROM information_schema.tables t
    WHERE t.table_schema = 'crm'
      AND t.table_type = 'BASE TABLE'
      AND t.table_name ILIKE '%tasks%'
      AND t.table_name NOT IN ('tasks', 'tasks_area')
      AND t.table_name NOT ILIKE '%\_log%' ESCAPE '\'
      AND EXISTS (
          SELECT 1
          FROM information_schema.columns c
          WHERE c.table_schema = 'crm'
            AND c.table_name = t.table_name
            AND c.column_name = 'task_key'
      )
    ORDER BY 1;

    IF NOT EXISTS (SELECT 1 FROM solntsevo_snapshots) THEN
        RAISE EXCEPTION 'no crm snapshot tables with task_key found';
    END IF;

    -- 1) snapshot.rayon
    FOR snap IN SELECT tbl FROM solntsevo_snapshots ORDER BY tbl
    LOOP
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'crm'
              AND table_name = snap
              AND column_name = 'rayon'
        ) INTO has_rayon;
        IF NOT has_rayon THEN
            CONTINUE;
        END IF;
        EXECUTE format(
            $q$
            INSERT INTO solntsevo_keys (task_key)
            SELECT DISTINCT s.task_key
            FROM crm.%I s
            WHERE s.task_key IS NOT NULL
              AND s.rayon ILIKE '%%солнцев%%'
            ON CONFLICT DO NOTHING
            $q$,
            snap
        );
    END LOOP;

    -- 2) geometry ∩ hood (via crm.v_task_geom when present)
    IF to_regclass('crm.v_task_geom') IS NOT NULL THEN
        INSERT INTO solntsevo_keys (task_key)
        SELECT DISTINCT g.task_key
        FROM crm.v_task_geom g
        JOIN solntsevo_hood h
          ON g.geom IS NOT NULL
         AND NOT ST_IsEmpty(g.geom)
         AND h.geom IS NOT NULL
         AND ST_Intersects(ST_MakeValid(g.geom), h.geom)
        WHERE g.task_key IS NOT NULL
        ON CONFLICT DO NOTHING;
    ELSE
        RAISE NOTICE 'crm.v_task_geom missing — skipping geom ∩ hood';
    END IF;

    SELECT count(*) INTO v_keys FROM solntsevo_keys;
    SELECT count(*) INTO v_tasks_before
    FROM crm.tasks t
    WHERE t.key IN (SELECT task_key FROM solntsevo_keys);

    INSERT INTO solntsevo_report VALUES
        ('hood', format('gid=%s %s', v_gid, v_rayon), 1),
        ('keys', 'solntsevo_keys', v_keys),
        ('crm.tasks', 'before (matching keys)', v_tasks_before);

    FOR snap IN SELECT tbl FROM solntsevo_snapshots ORDER BY tbl
    LOOP
        EXECUTE format(
            $q$
            SELECT count(*)
            FROM crm.%I s
            WHERE s.task_key IN (SELECT task_key FROM solntsevo_keys)
            $q$,
            snap
        ) INTO n_before;
        INSERT INTO solntsevo_report VALUES ('snapshot_before', snap, n_before);
    END LOOP;

    FOR snap IN SELECT tbl FROM solntsevo_snapshots ORDER BY tbl
    LOOP
        EXECUTE format(
            $q$
            DELETE FROM crm.%I s
            WHERE s.task_key IN (SELECT task_key FROM solntsevo_keys)
            $q$,
            snap
        );
        GET DIAGNOSTICS n_deleted = ROW_COUNT;
        INSERT INTO solntsevo_report VALUES ('deleted', snap, n_deleted);
    END LOOP;

    FOR snap IN SELECT tbl FROM solntsevo_snapshots ORDER BY tbl
    LOOP
        EXECUTE format(
            $q$
            SELECT count(*)
            FROM crm.%I s
            WHERE s.task_key IN (SELECT task_key FROM solntsevo_keys)
            $q$,
            snap
        ) INTO n_after;
        INSERT INTO solntsevo_report VALUES ('snapshot_after', snap, n_after);
        IF n_after <> 0 THEN
            RAISE EXCEPTION 'snapshot crm.% still has % rows for Solntsevo keys', snap, n_after;
        END IF;
    END LOOP;

    SELECT count(*) INTO n_tasks_after
    FROM crm.tasks t
    WHERE t.key IN (SELECT task_key FROM solntsevo_keys);
    INSERT INTO solntsevo_report VALUES
        ('crm.tasks', 'after (matching keys)', n_tasks_after);

    IF n_tasks_after <> v_tasks_before THEN
        RAISE EXCEPTION
            'crm.tasks count changed: before=% after=% (must not delete crm.tasks)',
            v_tasks_before, n_tasks_after;
    END IF;

    RAISE NOTICE 'solntsevo keys=% crm.tasks unchanged=%', v_keys, n_tasks_after;
END $$;

SELECT step, snapshot, n
FROM solntsevo_report
ORDER BY
    CASE step
        WHEN 'hood' THEN 1
        WHEN 'keys' THEN 2
        WHEN 'crm.tasks' THEN 3
        WHEN 'snapshot_before' THEN 4
        WHEN 'deleted' THEN 5
        WHEN 'snapshot_after' THEN 6
        ELSE 9
    END,
    snapshot;

\if :apply
COMMIT;
\echo === APPLIED (COMMIT) ===
\else
ROLLBACK;
\echo === DRY-RUN (ROLLBACK) ===
\endif
