# CRM Task Sync Recovery — 2026-07-09

**Server:** 77.222.63.161 (`/opt/monitor`)  
**Backup:** `/opt/monitor/reports/monitor_pre_crm_fix_20260709.dump` (156 MB)

## Summary

| Metric | Before | After |
|---|---:|---:|
| Linked split rows | 4457 (15.2%) | **29298 (100%)** |
| Gap | 24841 | **0** |
| `earthwork_id` tasks | 232 | **23433** |
| `localwork_id` tasks | 0 | **88** |
| `avr_mos_id` tasks | 15 | **1087** |
| False `tasked` | 9033 | **0** |

## Root cause

External CRM/QGIS deleted `crm.tasks` rows after recovery on 2026-07-07. FK `ON DELETE SET NULL` cleared `task_key`; false `tasked` on parents blocked nightly geom split (`crm_sync: inserted=0` since 2026-07-08).

## Recovery steps executed

1. `sql/31_data_mos_reset_false_tasked.sql`
2. Manual `sync_crm_tasks_after_etl` for items_62501, 62441, 62461, 2855
3. Deployed monitoring/backfill code + `sql/32_crm_tasks_delete_guard.sql`
4. Final audit: `reports/audit_final_20260709.md` on VPS

## New protections

- `backfill_data_mos_crm_tasks` manual job
- `crm_task_sync_audit` daily at 03:30 MSK
- `crm.tasks_deletion_log` + auto reset `tasked` on DELETE
- See `docs/crm_qgis_investigation.md` for CRM team checklist
