# CRM/QGIS investigation checklist — crm.tasks deletions

> **Handoff для WebCRM:** полное расследование и задачи на исправление —  
> [`docs/webcrm_tasks_deletion_investigation.md`](webcrm_tasks_deletion_investigation.md)  
> (корневая причина: `deploy/deploy.sh` повторно гоняет `sql/28_cleanup_link_orphan_tasks.sql`).

External CRM/QGIS has direct PostgreSQL access to the same `monitor` database as MONITOR collector.

## Symptoms when CRM deletes tasks

1. Rows disappear from `crm.tasks` (`earthwork_id`, `localwork_id`, `avr_mos_id` become NULL/absent).
2. `data_mos.items_*_{points,lines,polygons}.task_key` is set to NULL (`ON DELETE SET NULL`).
3. Parent `items_*.tasked` may stay `true` until `refresh_all_tasked_parents` or trigger `sql/32`.
4. Nightly `data_mos` ETL reports `geom split: 0` and may report `crm_sync: inserted=0` until false `tasked` is reset.

## What to search in CRM/QGIS codebase

```text
DELETE FROM crm.tasks
TRUNCATE crm.tasks
DROP TABLE crm.tasks
crm.tasks WHERE
```

Check operations triggered by:

- geometry edit / save in QGIS
- layer resync or reload
- "cleanup" of old or duplicate tasks
- bulk import that recreates tasks

## Audit on database

```sql
SELECT * FROM crm.tasks_deletion_log
ORDER BY deleted_at DESC
LIMIT 50;
```

Compare `application_name`, `db_user`, and `client_addr` with CRM service credentials.

Recent incidents (manual `psql` / `monitor`, SSH from `91.246.17.231`):

| Date (MSK) | Deleted | Pattern |
|---|---:|---|
| 2026-07-13 15:04 | 25 093 | Two batches (~24.6k + 485 oati) |
| 2026-07-16 10:12 | 26 958 | Two batches (~26.5k + 485 oati) |

Наиболее вероятный источник: **WebCRM `deploy/deploy.sh`** (цикл `psql -f sql/*.sql`), в т.ч. `sql/28_cleanup_link_orphan_tasks.sql`. Подробности — в [`webcrm_tasks_deletion_investigation.md`](webcrm_tasks_deletion_investigation.md).

## DB guard (sql/33)

- `DELETE` blocked when `user_created` contains `'etl'` (MONITOR-owned tasks).
- `crm.tasks_deletion_log.client_addr` records `inet_client_addr()` for allowed deletes.
- `RAISE WARNING` when a single statement deletes more than 100 rows.

Apply: `docker compose exec -T db psql -U monitor -d monitor < sql/33_crm_tasks_etl_delete_block.sql`

## Required CRM changes

1. **Do not hard-delete** rows where `user_created` contains `'etl'` (MONITOR-owned tasks).
2. Prefer soft-delete flag or detach (`task_key` unlink) instead of `DELETE`.
3. If delete is unavoidable, call MONITOR backfill: `python -m collector.scheduler --run backfill_data_mos_crm_tasks`.

## MONITOR recovery (ops)

```bash
docker compose exec -T db psql -U monitor -d monitor < sql/31_data_mos_reset_false_tasked.sql
docker compose exec collector python -m collector.scheduler --run backfill_data_mos_crm_tasks
docker compose exec collector python scripts/crm_task_sync_audit.py --output /app/reports/audit_final.md
```
