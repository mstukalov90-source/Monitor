-- Block DELETE of MONITOR-owned crm.tasks, log client IP, warn on mass DELETE.

ALTER TABLE crm.tasks_deletion_log
    ADD COLUMN IF NOT EXISTS client_addr INET;

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
        application_name,
        client_addr
    ) VALUES (
        OLD.key,
        OLD.earthwork_id,
        OLD.localwork_id,
        OLD.avr_mos_id,
        OLD.oati_id,
        current_user,
        current_setting('application_name', true),
        inet_client_addr()
    );
    RETURN OLD;
END;
$$;

CREATE OR REPLACE FUNCTION crm.block_etl_tasks_deletion()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.user_created IS NOT NULL AND 'etl' = ANY(OLD.user_created) THEN
        RAISE EXCEPTION
            'DELETE blocked: crm.tasks row is owned by MONITOR ETL (user_created contains etl). key=%, scoped_id=%',
            OLD.key,
            COALESCE(OLD.earthwork_id, OLD.oati_id, OLD.localwork_id, OLD.avr_mos_id);
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_crm_tasks_block_etl_delete ON crm.tasks;
CREATE TRIGGER trg_crm_tasks_block_etl_delete
    BEFORE DELETE ON crm.tasks
    FOR EACH ROW
    EXECUTE FUNCTION crm.block_etl_tasks_deletion();

CREATE OR REPLACE FUNCTION crm.warn_mass_tasks_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    n BIGINT;
BEGIN
    SELECT count(*) INTO n FROM deleted_rows;
    IF n > 100 THEN
        RAISE WARNING
            'crm.tasks mass DELETE: % rows removed by db_user=% application=% client=%',
            n,
            current_user,
            current_setting('application_name', true),
            inet_client_addr();
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_crm_tasks_mass_delete_warn ON crm.tasks;
CREATE TRIGGER trg_crm_tasks_mass_delete_warn
    AFTER DELETE ON crm.tasks
    REFERENCING OLD TABLE AS deleted_rows
    FOR EACH STATEMENT
    EXECUTE FUNCTION crm.warn_mass_tasks_delete();
