-- Ежедневный сброс флага analise в crm.tasks_area.
-- Безопасно запускать повторно (CREATE OR REPLACE).
--
-- Ручной запуск:
--   CALL crm.reset_tasks_area_analise();

CREATE SCHEMA IF NOT EXISTS crm;

CREATE OR REPLACE PROCEDURE crm.reset_tasks_area_analise()
LANGUAGE plpgsql
AS $$
DECLARE
    v_updated integer := 0;
BEGIN
    UPDATE crm.tasks_area
    SET analise = false
    WHERE analise IS DISTINCT FROM false;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE 'reset_tasks_area_analise: сброшено % строк', v_updated;
END;
$$;

COMMENT ON PROCEDURE crm.reset_tasks_area_analise() IS
'Сбрасывает crm.tasks_area.analise = false для всех строк, где флаг был true.';

-- pg_cron: каждый день в 03:00 MSK (cron.timezone = Europe/Moscow).
CREATE EXTENSION IF NOT EXISTS pg_cron;

DO $$
DECLARE
    v_jobid bigint;
BEGIN
    SELECT jobid INTO v_jobid
    FROM cron.job
    WHERE jobname = 'crm-tasks-area-reset-analise';

    IF v_jobid IS NOT NULL THEN
        PERFORM cron.unschedule(v_jobid);
    END IF;
END $$;

SELECT cron.schedule(
    'crm-tasks-area-reset-analise',
    '0 3 * * *',
    $$CALL crm.reset_tasks_area_analise()$$
);
