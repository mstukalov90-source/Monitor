-- TEST ONLY: apply on SWEB 77.222.63.161.
-- Do NOT run on prod 172.21.198.219.
--
-- WebCRM merge may store the same earthwork_id / oati_id / … on several
-- crm.tasks rows. ETL links via crm.tasks.key and data_mos.*.task_key,
-- so these unique indexes are not required.

DROP INDEX IF EXISTS crm.tasks_uq_photo_uuid;
DROP INDEX IF EXISTS crm.tasks_uq_photo_lens;
DROP INDEX IF EXISTS crm.tasks_uq_ogh_id;
DROP INDEX IF EXISTS crm.tasks_uq_oati_id;
DROP INDEX IF EXISTS crm.tasks_uq_earthwork_id;
DROP INDEX IF EXISTS crm.tasks_uq_localwork_id;
DROP INDEX IF EXISTS crm.tasks_uq_avr_mos_id;
