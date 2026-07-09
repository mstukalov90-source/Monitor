# CRM Task Sync Baseline — incident 2026-07-09

Generated: 2026-07-09 11:05 UTC (VPS audit before recovery)

## Summary

- Split rows with geom: **29298**
- Linked (`task_key` set): **4457** (15.2%)
- Gap (geom without `task_key`): **24841**
- False `tasked` parents: **9033**
- Duplicate `task_key` in split tables: **0**

## CRM scoped tasks

- `earthwork_id`: total=**232** (expected ~23433)
- `localwork_id`: total=**0** (expected ~88)
- `avr_mos_id`: total=**15** (expected ~1087)

## Likely cause

External CRM/QGIS deleted `crm.tasks` rows after successful recovery on 2026-07-07. Nightly ETL since 2026-07-08 reports `crm_sync: inserted=0 linked=0` with false `tasked` blocking geom split.

Backup: `/opt/monitor/reports/monitor_pre_crm_fix_20260709.dump` (156 MB)
