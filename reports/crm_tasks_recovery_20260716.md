# CRM tasks recovery — 2026-07-16

## Incident

- **When:** 2026-07-16 10:12:05–10:12:17 MSK
- **How:** `psql` as `monitor` (not ETL)
- **SSH:** `91.246.17.231` (same IP as 2026-07-13 incident)
- **Deleted:** 26 958 tasks (earthwork 24 175, avr 2 034, oati 485, localwork 264)

## Before recovery

| Metric | Value |
|---|---:|
| Split geom rows | 31 500 |
| Linked (`task_key`) | 4 542 (14.4%) |
| Gap | 26 958 |

Report: `reports/audit_20260716_before.md`

## Recovery steps

1. `sql/31_data_mos_reset_false_tasked.sql`
2. `backfill_data_mos_crm_tasks` — **6.3 s**, inserted=26 958, linked=26 958

## After recovery

| Metric | Value |
|---|---:|
| Split geom rows | 31 500 |
| Linked (`task_key`) | 31 500 (100%) |
| Gap | **0** |
| False `tasked` | 0 |
| Duplicate `task_key` | 0 |

`crm.tasks` scoped counts: earthwork 24 185, oati 5 032, localwork 264, avr 2 036 (total 43 126).

Report: `reports/audit_20260716_after.md`

## Delete source investigation

- VPS `/root/.bash_history`: no `DELETE FROM crm.tasks` (only unrelated `passport_db` queries).
- `crm.tasks_deletion_log`: only `db_user=monitor`, `application_name=psql`; no SQL text stored.
- Pattern matches 2026-07-13: two DELETE batches in ~12 s, second batch exactly 485 oati tasks.
- Likely manual cleanup from SSH client on `91.246.17.231`, not CRM/QGIS service and not nightly `data_mos`.

## Hardening applied

`sql/33_crm_tasks_etl_delete_block.sql`:

- Block `DELETE` for `user_created @> '{etl}'`
- Log `client_addr` in `tasks_deletion_log`
- `WARNING` on mass DELETE (>100 rows per statement)
