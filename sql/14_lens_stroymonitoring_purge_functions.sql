-- Purge functions for stroymonitoring.boundaries_aip and lens.reports.
-- Safe to run multiple times (CREATE OR REPLACE).

CREATE SCHEMA IF NOT EXISTS stroymonitoring;
CREATE SCHEMA IF NOT EXISTS lens;

CREATE OR REPLACE FUNCTION stroymonitoring.purge_boundaries_aip()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    target regclass;
    cnt_status_vveden integer := 0;
    cnt_status_not_started integer := 0;
    cnt_metro integer := 0;
    cnt_actual_object integer := 0;
    deleted integer := 0;
BEGIN
    target := to_regclass('stroymonitoring.boundaries_aip');
    IF target IS NULL THEN
        RAISE NOTICE 'purge_boundaries_aip: таблица stroymonitoring.boundaries_aip не существует, пропуск';
        RETURN 0;
    END IF;

    SELECT COUNT(*) INTO cnt_status_vveden
    FROM stroymonitoring.boundaries_aip
    WHERE btrim(status::text) IN ('Введён', 'Введен');

    SELECT COUNT(*) INTO cnt_status_not_started
    FROM stroymonitoring.boundaries_aip
    WHERE btrim(status::text) = 'Работы не начаты';

    SELECT COUNT(*) INTO cnt_metro
    FROM stroymonitoring.boundaries_aip
    WHERE btrim(fno_level1_name::text) = 'Метро';

    SELECT COUNT(*) INTO cnt_actual_object
    FROM stroymonitoring.boundaries_aip
    WHERE actual_object IS FALSE;

    RAISE NOTICE 'purge_boundaries_aip: условие status = Введён: % строк', cnt_status_vveden;
    RAISE NOTICE 'purge_boundaries_aip: условие status = Работы не начаты: % строк', cnt_status_not_started;
    RAISE NOTICE 'purge_boundaries_aip: условие fno_level1_name = Метро: % строк', cnt_metro;
    RAISE NOTICE 'purge_boundaries_aip: условие actual_object = false: % строк', cnt_actual_object;

    DELETE FROM stroymonitoring.boundaries_aip
    WHERE btrim(status::text) IN ('Введён', 'Введен')
       OR btrim(status::text) = 'Работы не начаты'
       OR btrim(fno_level1_name::text) = 'Метро'
       OR actual_object IS FALSE;

    GET DIAGNOSTICS deleted = ROW_COUNT;
    RAISE NOTICE 'purge_boundaries_aip: всего удалено % строк', deleted;
    RETURN deleted;

EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'purge_boundaries_aip: ошибка: %', SQLERRM;
    RAISE;
END;
$$;

COMMENT ON FUNCTION stroymonitoring.purge_boundaries_aip() IS
'Очистка stroymonitoring.boundaries_aip. Удаляет строки, если выполняется любое из условий:
1) status = ''Введён'' (также ''Введен'');
2) status = ''Работы не начаты'';
3) fno_level1_name = ''Метро'';
4) actual_object = false.';

CREATE OR REPLACE FUNCTION lens.purge_reports()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    target regclass;
    cnt_received_at integer := 0;
    cnt_processing_status integer := 0;
    deleted integer := 0;
BEGIN
    target := to_regclass('lens.reports');
    IF target IS NULL THEN
        RAISE NOTICE 'purge_reports: таблица lens.reports не существует, пропуск';
        RETURN 0;
    END IF;

    SELECT COUNT(*) INTO cnt_received_at
    FROM lens.reports
    WHERE received_at < NOW() - INTERVAL '14 days';

    SELECT COUNT(*) INTO cnt_processing_status
    FROM lens.reports
    WHERE processing_status = 'Неактуально';

    RAISE NOTICE 'purge_reports: условие received_at старше 14 дней: % строк', cnt_received_at;
    RAISE NOTICE 'purge_reports: условие processing_status = Неактуально: % строк', cnt_processing_status;

    DELETE FROM lens.reports
    WHERE received_at < NOW() - INTERVAL '14 days'
       OR processing_status = 'Неактуально';

    GET DIAGNOSTICS deleted = ROW_COUNT;
    RAISE NOTICE 'purge_reports: всего удалено % строк', deleted;
    RETURN deleted;

EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'purge_reports: ошибка: %', SQLERRM;
    RAISE;
END;
$$;

COMMENT ON FUNCTION lens.purge_reports() IS
'Очистка lens.reports. Удаляет строки, если выполняется любое из условий:
1) received_at старше 14 дней;
2) processing_status = ''Неактуально''.';
