# CRM Task Sync Final 20260709

Generated: 2026-07-09 11:09 UTC

## Summary

- Split rows with geom: **29298**
- Linked (`task_key` set): **29298** (100.0%)
- Gap (geom without `task_key`): **0**
- False `tasked` parents: **0**
- Duplicate `task_key` in split tables: **0**

## Split tables

| service | layer | total | geom | linked | gap | crm_match | would_insert |
|---|---|---:|---:|---:|---:|---:|---:|
| items_2855 | points | 1451 | 1451 | 1451 | 0 | 1451 | 0 |
| items_2855 | lines | 1982 | 1982 | 1982 | 0 | 1982 | 0 |
| items_2855 | polygons | 1257 | 1257 | 1257 | 0 | 1257 | 0 |
| items_62501 | points | 8773 | 8773 | 8773 | 0 | 8773 | 0 |
| items_62501 | lines | 9579 | 9579 | 9579 | 0 | 9579 | 0 |
| items_62501 | polygons | 5081 | 5081 | 5081 | 0 | 5081 | 0 |
| items_62441 | points | 85 | 85 | 85 | 0 | 85 | 0 |
| items_62441 | lines | 0 | 0 | 0 | 0 | 0 | 0 |
| items_62441 | polygons | 3 | 3 | 3 | 0 | 3 | 0 |
| items_62461 | points | 0 | 0 | 0 | 0 | 0 | 0 |
| items_62461 | lines | 614 | 614 | 614 | 0 | 614 | 0 |
| items_62461 | polygons | 473 | 473 | 473 | 0 | 473 | 0 |

## False tasked parents

- `items_2855`: **0**
- `items_62501`: **0**
- `items_62441`: **0**
- `items_62461`: **0**

## CRM scoped tasks (point/line/polygon)

- `oati_id`: point=1451, line=1982, polygon=1257, total=4690
- `earthwork_id`: point=8773, line=9579, polygon=5081, total=23433
- `localwork_id`: point=85, line=0, polygon=3, total=88
- `avr_mos_id`: point=0, line=614, polygon=473, total=1087

## Duplicate task_key

- None

## Multi-match restore candidates (global_id+geom)

- `data_mos.items_2855_points` global_id=5073799413: **5** rows
- `data_mos.items_2855_points` global_id=5073799413: **4** rows
- `data_mos.items_2855_points` global_id=5088126386: **3** rows
- `data_mos.items_2855_points` global_id=2878249570: **3** rows
- `data_mos.items_2855_points` global_id=2645664649: **2** rows
- `data_mos.items_2855_lines` global_id=2608622163: **2** rows
- `data_mos.items_2855_lines` global_id=2608622397: **2** rows
- `data_mos.items_2855_lines` global_id=2666339853: **2** rows
- `data_mos.items_2855_lines` global_id=2666339897: **2** rows
- `data_mos.items_2855_lines` global_id=1068908436: **2** rows
- `data_mos.items_2855_polygons` global_id=2608622342: **2** rows
- `data_mos.items_2855_polygons` global_id=2658377727: **2** rows
- `data_mos.items_2855_polygons` global_id=2666339853: **2** rows
- `data_mos.items_2855_polygons` global_id=2671349303: **2** rows
- `data_mos.items_2855_polygons` global_id=1026032774: **2** rows
- `data_mos.items_62501_points` global_id=2878244430: **3** rows
- `data_mos.items_62501_points` global_id=2767247601: **3** rows
- `data_mos.items_62501_points` global_id=2783503708: **2** rows
- `data_mos.items_62501_points` global_id=2807526719: **2** rows
- `data_mos.items_62501_points` global_id=2798948507: **2** rows

## Recent job runs

- **data_mos_62501** `success` @ 2026-07-09 00:31:42.259510+00:00: Loaded 7988 features, purged 1726 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped), crm_sync: inserted=0 linked=0 tasked_parents=7975
- **data_mos_62461** `success` @ 2026-07-09 00:02:19.322218+00:00: Loaded 3293 features, purged 2298 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped), crm_sync: inserted=0 linked=0 tasked_parents=1086
- **data_mos_2855** `success` @ 2026-07-09 00:01:43.059545+00:00: Loaded 3262 features, purged 1251 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped), crm_sync: inserted=0 linked=0 tasked_parents=2945
- **data_mos_62501** `success` @ 2026-07-08 00:32:53.596332+00:00: Loaded 7988 features, purged 1726 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped), crm_sync: inserted=0 linked=0 tasked_parents=7975
- **data_mos_62461** `success` @ 2026-07-08 00:02:16.736539+00:00: Loaded 3293 features, purged 2298 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped), crm_sync: inserted=0 linked=0 tasked_parents=1086
- **data_mos_2855** `success` @ 2026-07-08 00:01:40.316724+00:00: Loaded 3264 features, purged 1252 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped), crm_sync: inserted=0 linked=0 tasked_parents=2945
- **data_mos_2855** `success` @ 2026-07-07 18:53:05.407348+00:00: Loaded 3264 features, purged 1252 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped), crm_sync: inserted=485 linked=485 tasked_parents=2945
- **data_mos_62461** `success` @ 2026-07-07 18:51:02.910673+00:00: Loaded 3293 features, purged 2298 archived rows, derived 91 polygons in items_*, geom split: 0 points, 614 lines, 473 polygons (0 skipped), crm_sync: inserted=1087 linked=1087 tasked_parents=1086
- **data_mos_62441** `success` @ 2026-07-07 18:50:21.169511+00:00: Loaded 49086 features, purged 48998 archived rows, geom split: 85 points, 0 lines, 3 polygons (0 skipped), crm_sync: inserted=88 linked=88 tasked_parents=88
- **data_mos_62501** `success` @ 2026-07-07 18:37:53.821499+00:00: Loaded 7988 features, purged 1726 archived rows, derived 1713 polygons in items_*, geom split: 8773 points, 9579 lines, 5081 polygons (0 skipped), crm_sync: inserted=23433 linked=23433 tasked_parents=
