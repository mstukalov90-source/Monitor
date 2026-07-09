-- Log crm.tasks deletions and reset false tasked flags on data_mos parents.

CREATE TABLE IF NOT EXISTS crm.tasks_deletion_log (
    id              BIGSERIAL PRIMARY KEY,
    deleted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    task_key        UUID,
    earthwork_id    TEXT,
    localwork_id    TEXT,
    avr_mos_id      TEXT,
    oati_id         TEXT,
    db_user         TEXT NOT NULL DEFAULT current_user,
    application_name TEXT
);

CREATE OR REPLACE FUNCTION crm.log_tasks_deletion()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO crm.tasks_deletion_log (
        task_key,
        earthwork_id,
        localwork_id,
        avr_mos_id,
        oati_id,
        db_user,
        application_name
    ) VALUES (
        OLD.key,
        OLD.earthwork_id,
        OLD.localwork_id,
        OLD.avr_mos_id,
        OLD.oati_id,
        current_user,
        current_setting('application_name', true)
    );
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_crm_tasks_deletion_log ON crm.tasks;
CREATE TRIGGER trg_crm_tasks_deletion_log
    BEFORE DELETE ON crm.tasks
    FOR EACH ROW
    EXECUTE FUNCTION crm.log_tasks_deletion();

CREATE OR REPLACE FUNCTION crm.reset_tasked_after_tasks_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    parent_tbl TEXT;
BEGIN
    FOREACH parent_tbl IN ARRAY ARRAY[
        'items_2855', 'items_62501', 'items_62441', 'items_62461'
    ]
    LOOP
        EXECUTE format($sql$
            UPDATE data_mos.%I p
            SET tasked = (
                EXISTS (
                    SELECT 1 FROM data_mos.%I_points c
                    WHERE c.source_id = p.id AND c.task_key IS NOT NULL
                )
                OR EXISTS (
                    SELECT 1 FROM data_mos.%I_lines c
                    WHERE c.source_id = p.id AND c.task_key IS NOT NULL
                )
                OR EXISTS (
                    SELECT 1 FROM data_mos.%I_polygons c
                    WHERE c.source_id = p.id AND c.task_key IS NOT NULL
                )
            )
        $sql$, parent_tbl, parent_tbl, parent_tbl, parent_tbl);
    END LOOP;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_crm_tasks_after_delete_reset_tasked ON crm.tasks;
CREATE TRIGGER trg_crm_tasks_after_delete_reset_tasked
    AFTER DELETE ON crm.tasks
    FOR EACH STATEMENT
    EXECUTE FUNCTION crm.reset_tasked_after_tasks_delete();
