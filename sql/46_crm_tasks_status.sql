-- Denormalized crm.tasks.status from snapshot tables.
-- Idempotent. Safe to re-run.
--
-- Apply only on SWEB test 77.222.63.161 — do not run on prod 172.21.198.219.
--
-- Backfill (also runs at the end of this file):
--   SET statement_timeout = '30min';
--   CALL crm.refresh_task_status();
--
-- Codes: active / field / legal / illegal / clear / delay
-- DELETE from a snapshot with no remaining snapshots → status = active.

CREATE SCHEMA IF NOT EXISTS crm;

-- ---------------------------------------------------------------------------
-- Column + check + index
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF to_regclass('crm.tasks') IS NULL THEN
        RAISE NOTICE 'crm.tasks missing, skip status column';
        RETURN;
    END IF;

    ALTER TABLE crm.tasks
        ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

    ALTER TABLE crm.tasks
        DROP CONSTRAINT IF EXISTS crm_tasks_status_check;
    ALTER TABLE crm.tasks
        ADD CONSTRAINT crm_tasks_status_check
        CHECK (status IN ('active', 'field', 'legal', 'illegal', 'clear', 'delay'));

    CREATE INDEX IF NOT EXISTS idx_crm_tasks_status
        ON crm.tasks (status);

    COMMENT ON COLUMN crm.tasks.status IS
        'Task state: active=Активная, field=В поле, legal=Закрыта легально, illegal=закрыта нелегально, clear=Разрытие отсутствует, delay=Отложенные';
END $$;

-- ---------------------------------------------------------------------------
-- Compute status for one task_key (no snapshots → active)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION crm.task_status_for_key(p_key uuid)
RETURNS text
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_found boolean;
    rec record;
BEGIN
    IF p_key IS NULL THEN
        RETURN 'active';
    END IF;

    FOR rec IN
        SELECT * FROM (VALUES
            ('tasks_done_legal', 'legal'),
            ('tasks_done_illegal', 'illegal'),
            ('tasks_clear', 'clear'),
            ('tasks_delay', 'delay'),
            ('tasks_field', 'field')
        ) AS x(snap, code)
    LOOP
        IF to_regclass(format('crm.%I', rec.snap)) IS NULL THEN
            CONTINUE;
        END IF;
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM crm.%I s WHERE s.task_key = $1)',
            rec.snap
        ) INTO v_found USING p_key;
        IF v_found THEN
            RETURN rec.code;
        END IF;
    END LOOP;

    RETURN 'active';
END;
$$;

COMMENT ON FUNCTION crm.task_status_for_key(uuid) IS
    'crm.tasks.status from snapshot tables; active when none match.';

CREATE OR REPLACE PROCEDURE crm.refresh_task_status()
LANGUAGE plpgsql
AS $$
DECLARE
    v_updated integer := 0;
BEGIN
    IF to_regclass('crm.tasks') IS NULL THEN
        RAISE NOTICE 'crm.tasks missing, skip refresh_task_status';
        RETURN;
    END IF;

    UPDATE crm.tasks t
    SET status = s.st
    FROM (
        SELECT key, crm.task_status_for_key(key) AS st
        FROM crm.tasks
    ) s
    WHERE t.key = s.key
      AND t.status IS DISTINCT FROM s.st;
    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE 'refresh_task_status: updated=%', v_updated;
END;
$$;

COMMENT ON PROCEDURE crm.refresh_task_status() IS
    'Recompute crm.tasks.status from current snapshot rows.';

-- ---------------------------------------------------------------------------
-- Triggers: snapshots INSERT / UPDATE task_key / DELETE → including active
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION crm.trg_snapshot_refresh_task_status()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_new uuid;
    v_old uuid;
    v_st text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_new := NULL;
        v_old := OLD.task_key;
    ELSIF TG_OP = 'UPDATE' THEN
        v_new := NEW.task_key;
        v_old := OLD.task_key;
    ELSE
        v_new := NEW.task_key;
        v_old := NULL;
    END IF;

    IF v_new IS NOT NULL THEN
        v_st := crm.task_status_for_key(v_new);
        UPDATE crm.tasks
        SET status = v_st
        WHERE key = v_new
          AND status IS DISTINCT FROM v_st;
    END IF;

    IF v_old IS NOT NULL AND v_old IS DISTINCT FROM v_new THEN
        v_st := crm.task_status_for_key(v_old);
        UPDATE crm.tasks
        SET status = v_st
        WHERE key = v_old
          AND status IS DISTINCT FROM v_st;
    END IF;

    RETURN NULL;
END;
$$;

DO $$
DECLARE
    snap text;
    trg_name text;
BEGIN
    IF to_regclass('crm.tasks') IS NULL THEN
        RETURN;
    END IF;

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
        trg_name := 'trg_crm_' || snap || '_refresh_status';
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON crm.%I', trg_name, snap);
        EXECUTE format(
            $q$
            CREATE TRIGGER %I
                AFTER INSERT OR UPDATE OF task_key OR DELETE
                ON crm.%I
                FOR EACH ROW
                EXECUTE FUNCTION crm.trg_snapshot_refresh_task_status()
            $q$,
            trg_name,
            snap
        );
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Backfill existing rows
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF to_regclass('crm.tasks') IS NULL THEN
        RETURN;
    END IF;
    CALL crm.refresh_task_status();
END $$;
