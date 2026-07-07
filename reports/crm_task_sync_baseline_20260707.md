# CRM Task Sync Baseline

Generated: 2026-07-07 18:27 UTC

## Summary

- Split rows with geom: **29377**
- Linked (`task_key` set): **4205** (14.3%)
- Gap (geom without `task_key`): **25172**
- False `tasked` parents: **9187**
- Duplicate `task_key` in split tables: **0**

## Split tables

| service | layer | total | geom | linked | gap | crm_match | would_insert |
|---|---|---:|---:|---:|---:|---:|---:|
| items_2855 | points | 1451 | 1451 | 1318 | 133 | 1318 | 133 |
| items_2855 | lines | 1982 | 1982 | 1717 | 265 | 1717 | 265 |
| items_2855 | polygons | 1336 | 1336 | 1170 | 166 | 1170 | 166 |
| items_62501 | points | 8773 | 8773 | 0 | 8773 | 0 | 8773 |
| items_62501 | lines | 9579 | 9579 | 0 | 9579 | 0 | 9579 |
| items_62501 | polygons | 5081 | 5081 | 0 | 5081 | 0 | 5081 |
| items_62441 | points | 85 | 85 | 0 | 85 | 0 | 85 |
| items_62441 | lines | 0 | 0 | 0 | 0 | 0 | 0 |
| items_62441 | polygons | 3 | 3 | 0 | 3 | 0 | 3 |
| items_62461 | points | 0 | 0 | 0 | 0 | 0 | 0 |
| items_62461 | lines | 614 | 614 | 0 | 614 | 0 | 614 |
| items_62461 | polygons | 473 | 473 | 0 | 473 | 0 | 473 |

## False tasked parents

- `items_2855`: **38**
- `items_62501`: **7975**
- `items_62441`: **88**
- `items_62461`: **1086**

## CRM scoped tasks (point/line/polygon)

- `oati_id`: point=1318, line=1717, polygon=1170, total=4205
- `earthwork_id`: point=0, line=0, polygon=0, total=0
- `localwork_id`: point=0, line=0, polygon=0, total=0
- `avr_mos_id`: point=0, line=0, polygon=0, total=0

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
- `data_mos.items_2855_polygons` global_id=1733420709: **2** rows
- `data_mos.items_2855_polygons` global_id=2580161784: **2** rows
- `data_mos.items_2855_polygons` global_id=2608622342: **2** rows
- `data_mos.items_2855_polygons` global_id=2608622397: **2** rows
- `data_mos.items_2855_polygons` global_id=1026032774: **2** rows
- `data_mos.items_62501_points` global_id=2878244430: **3** rows
- `data_mos.items_62501_points` global_id=2767247601: **3** rows
- `data_mos.items_62501_points` global_id=2783503708: **2** rows
- `data_mos.items_62501_points` global_id=2807526719: **2** rows
- `data_mos.items_62501_points` global_id=2798948507: **2** rows

## Recent job runs

- **data_mos_62441** `success` @ 2026-07-07 13:32:54.516361+00:00: Loaded 49086 features, purged 48998 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped)
- **data_mos_62441** `success` @ 2026-07-07 13:06:25.701944+00:00: Loaded 49086 features, purged 48998 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped)
- **data_mos_62501** `success` @ 2026-07-07 12:56:18.490297+00:00: Loaded 7988 features, purged 1726 archived rows, geom split: 0 points, 0 lines, 0 polygons (0 skipped)
- **data_mos_62461** `success` @ 2026-07-07 12:47:39.874709+00:00: Loaded 3293 features, purged 2298 archived rows, derived 82 polygons in items_*, geom split: 0 points, 579 lines, 446 polygons (0 skipped)
- **data_mos_62441** `success` @ 2026-07-07 12:47:12.140338+00:00: Loaded 49086 features, purged 48998 archived rows, geom split: 83 points, 0 lines, 3 polygons (0 skipped)
- **data_mos_62441** `failed` @ 2026-07-07 12:47:12.120645+00:00: deadlock detected
DETAIL:  Process 1462329 waits for AccessExclusiveLock on relation 247180 of database 94045; blocked by process 1461827.
Process 1461827 waits for AccessExclusiveLock on relation 247
- **data_mos_62501** `success` @ 2026-07-07 12:35:37.922158+00:00: Loaded 7988 features, purged 1726 archived rows, derived 1625 polygons in items_*, geom split: 8400 points, 9124 lines, 4879 polygons (0 skipped)
- **data_mos_2855** `success` @ 2026-07-07 12:30:35.596678+00:00: Loaded 3764 features, purged 1356 archived rows, derived 90 polygons in items_*, geom split: 312 points, 291 lines, 178 polygons (0 skipped)
- **data_mos_2855** `success` @ 2026-07-07 12:21:53.999430+00:00: Loaded 3264 features, purged 1252 archived rows, derived 472 polygons in items_*, geom split: 768 points, 1072 lines, 824 polygons (0 skipped)
- **data_mos_2855** `success` @ 2026-07-07 10:16:52.371805+00:00: Loaded 3764 features, purged 1356 archived rows, derived 697 polygons in items_*, geom split: 1331 points, 1717 lines, 1248 polygons (0 skipped)
