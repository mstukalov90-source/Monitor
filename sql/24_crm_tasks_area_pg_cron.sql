-- pg_cron: квартальный автозапуск crm.refresh_tasks_area_quarterly().
-- Требует shared_preload_libraries=pg_cron и cron.database_name=monitor (docker-compose command).
-- Безопасно запускать повторно.

CREATE EXTENSION IF NOT EXISTS pg_cron;

DO $$
DECLARE
    v_jobid bigint;
BEGIN
    SELECT jobid INTO v_jobid
    FROM cron.job
    WHERE jobname = 'crm-tasks-area-quarterly';

    IF v_jobid IS NOT NULL THEN
        PERFORM cron.unschedule(v_jobid);
    END IF;
END $$;

SELECT cron.schedule(
    'crm-tasks-area-quarterly',
    '0 0 1 1,4,7,10 *',
    $$CALL crm.refresh_tasks_area_quarterly()$$
);
