# MONITOR - avtomaticheskiy sborshik dannykh

Docker-okruzhenie s PostGIS i planirovshchikom ETL-zadach.

## Raspisanie (Europe/Moscow)

| Vremya | Zadacha | Opisanie |
|-------|--------|----------|
| 03:00 | `data_mos` | Vse 8 eksportov `data_mos_export_*.py` → `data_mos.items_<id>`; zatem `ogh_disruption`: esli est `mggt_dgn/mggt_dgn.geojson` — upsert v `odh_export."ogh-disruption"` po `(source_json, lon, lat)` — slivanie tolko pri sovpadenii koordinat, udalenie fayla |
| 04:00 | `lens_pipeline` | `lens_sync` (SPS → `lens`), zatem `stroymonitoring_sync` (web_geo → `stroymonitoring`) |
| 05:00 | `genplan` | Import `jsons_genplan/*.json` v 4 tablitsy `genplan.*` (klassifikatsiya po strukture JSON), udalenie obrabotannykh faylov |
| 06:00 | `vector_stroy_url_222` | Esli v korne proekta est `url_222_wgs.geojson` — upsert v `vector_stroy.url_222` po `uuid`, zatem udalenie fayla; inache propusk |

Posle kazhdogo eksporta udalyayutsya sootvetstvuyushchie `.geojson` i `.gpkg`. Polnyy progon 8 servisov mozhet zanyat znachitelnoe vremya do starta `lens_sync` v 04:00.

### Servisy data.mos.ru

| Job | Skript | Tablitsa | Purge |
|-----|--------|----------|-------|
| `data_mos_2855` | `data_mos_export_2855.py` | `items_2855` | da |
| `data_mos_2941` | `data_mos_export_2941.py` | `items_2941` | da |
| `data_mos_62461` | `data_mos_export_62461.py` | `items_62461` | da |
| `data_mos_62501` | `data_mos_export_62501.py` | `items_62501` | da |
| `data_mos_1498` | `data_mos_export_1498.py` | `items_1498` | net |
| `data_mos_1500` | `data_mos_export_1500.py` | `items_1500` | net |
| `data_mos_2386` | `data_mos_export_2386.py` | `items_2386` | net |
| `data_mos_62441` | `data_mos_export_62441.py` | `items_62441` | da |

Kolonki v `data_mos.items_*` sozdayutsya **dinamicheski** iz klyuchey GeoJSON (snake_case). Bazovye polya: `id`, `geom`, `loaded_at`.

## Ochistka arkhivnykh zapisey (purge)

Dlya vybrannykh servisov. Posle uspeshnoy zagruzki udalyayutsya ustarevshie stroki (timezone `TZ`, po umolchaniyu Europe/Moscow). Pustye `NULL` / `''` v pole-filtre **ne udalyayutsya**.

| Tablitsa | Pole | Pravilo |
|----------|------|---------|
| `items_2855` | `work_end_date` | data <= segodnya minus 1 mesyats |
| `items_2941` | `plan_year_construction_complete` | god < tekushchiy god |
| `items_62461` | `work_end_date` | kak u 2855 |
| `items_62501` | `work_end_date` | kak u 2855 |
| `items_62441` | `actual_end_date` | data <= segodnya minus 1 mesyats |

### lens i stroymonitoring (OR-usloviya)

Posle uspeshnoy sinhronizatsii v 04:00. Usloviya v ramkah tablitsy obedineny cherez **OR** — stroka udalyaetsya, esli podkhodit khotya by pod odno. Podschety po kazhdomu usloviyu v logakh mogut perekryvat'sya.

| Tablitsa | Usloviya (OR) | Kogda vyzyvaetsya |
|----------|---------------|-------------------|
| `stroymonitoring.boundaries_aip` | `status` = «Введён» (ili «Введен»); `status` = «Работы не начаты»; `fno_level1_name` = «Метро»; `actual_object` = false | posle `stroymonitoring_sync` |
| `lens.reports` | `received_at` starshe 14 dney; `processing_status` = «Неактуально» | posle `lens_sync` |

Migratsii funktsiy ochistki:

```bash
docker compose exec -T db psql -U monitor -d monitor < sql/05_data_mos_purge_functions.sql
docker compose exec -T db psql -U monitor -d monitor < sql/14_lens_stroymonitoring_purge_functions.sql
```

Primery vyzova:

```sql
-- Pryamoy vyzov
SELECT stroymonitoring.purge_boundaries_aip();
SELECT lens.purge_reports();

-- Proverka bez sokhraneniya (otkat)
BEGIN;
SELECT stroymonitoring.purge_boundaries_aip();
SELECT count(*) FROM stroymonitoring.boundaries_aip;
ROLLBACK;

-- Predprosmotr: skolko strok popadet pod kazhdoe uslovie
SELECT
  count(*) FILTER (WHERE btrim(status::text) IN ('Введён', 'Введен')) AS by_status_vveden,
  count(*) FILTER (WHERE btrim(status::text) = 'Работы не начаты') AS by_status_not_started,
  count(*) FILTER (WHERE btrim(fno_level1_name::text) = 'Метро') AS by_metro,
  count(*) FILTER (WHERE actual_object IS FALSE) AS by_actual_object
FROM stroymonitoring.boundaries_aip;

SELECT
  count(*) FILTER (WHERE received_at < NOW() - INTERVAL '14 days') AS by_received_at,
  count(*) FILTER (WHERE processing_status = 'Неактуально') AS by_processing_status
FROM lens.reports;
```

## Pайплайн data_mos (2855, 62441, 62461, 62501)

Dlya kazhdogo servisa posledovatelno:

1. `data_mos_export_<id>.py` → GeoJSON
2. Zagruzka v `data_mos.items_<id>`
3. `purge_archived` po date
4. `derive_polygons_from_lines` (Python) — line→polygon dlya `LineString` / `MultiLineString` i dlya liniy vnutri `GeometryCollection` → novye stroki v `items_*` s `derived_from_id`
5. `rebuild_geom_split` — marshrutizatsiya v `*_points`, `*_lines`, `*_polygons` (`ST_MakeValid`, `ST_Dump` dlya chastey `GeometryCollection`; bez povtornogo line→polygon)

| Ishod | Naznachenie |
|-------|-------------|
| `data_mos.items_2855` | `items_2855_points`, `items_2855_lines`, `items_2855_polygons` |
| `data_mos.items_62441` | `items_62441_points`, `items_62441_lines`, `items_62441_polygons` |
| `data_mos.items_62461` | `items_62461_points`, `items_62461_lines`, `items_62461_polygons` |
| `data_mos.items_62501` | `items_62501_points`, `items_62501_lines`, `items_62501_polygons` |

Polya v tipizirovannykh tablitsakh: `source_id`, v `*_polygons` takzhe `derived_from_id` (kopiya iz `items_*`).

Migratsiya obolochek tablits:

```bash
docker compose exec -T db psql -U monitor -d monitor < sql/09_data_mos_geom_split.sql
```

`sql/07_line_to_polygon.sql` — tolko dlya ruchnykh SQL-zaprosov v psql, ne dlya ETL.

Proverka:

```sql
SELECT ST_GeometryType(geom), count(*)
FROM data_mos.items_2855_points
GROUP BY 1;

SELECT count(*) FROM data_mos.items_2855_lines;
SELECT count(*) FROM data_mos.items_2855_polygons WHERE derived_from_id IS NOT NULL;

SELECT count(*) FROM data_mos.items_2855
WHERE ST_GeometryType(geom) = 'ST_GeometryCollection';

SELECT count(*) FROM data_mos.items_2855_points p
JOIN data_mos.items_2855 s ON s.id = p.source_id
WHERE ST_GeometryType(s.geom) = 'ST_GeometryCollection';

SELECT p.source_id, p.derived_from_id, ST_GeometryType(l.geom), ST_GeometryType(p.geom)
FROM data_mos.items_2855_polygons p
JOIN data_mos.items_2855_lines l ON l.source_id = p.derived_from_id
WHERE p.derived_from_id IS NOT NULL
LIMIT 5;
```

## Bystryy start

```bash
cp .env.example .env
docker compose up -d --build
```

Na sushchestvuyushchey BD primenite migratsii (06, 08, 09 — bez DROP, bezopasno; 10 — DROP `genplan.responses`):

```bash
docker compose exec -T db psql -U monitor -d monitor < sql/06_data_mos_extra_tables.sql
docker compose exec -T db psql -U monitor -d monitor < sql/08_reports_geom.sql
docker compose exec -T db psql -U monitor -d monitor < sql/09_data_mos_geom_split.sql
docker compose exec -T db psql -U monitor -d monitor < sql/10_genplan_multi_tables.sql
docker compose exec -T db psql -U monitor -d monitor < sql/14_lens_stroymonitoring_purge_functions.sql
docker compose exec collector python -m collector.scheduler --run data_mos
```

Dlya polnogo peresozdaniya pervykh chetyrekh tablits (DROP dannykh): `sql/04_data_mos_dynamic_tables.sql`.

## Ruchnoy zapusk zadach

```bash
# vse 8 eksportov podryad
docker compose exec collector python -m collector.scheduler --run data_mos

# odin servis
docker compose exec collector python -m collector.scheduler --run data_mos_1498

# lens + stroymonitoring (kak v 04:00)
docker compose exec collector python -m collector.scheduler --run lens_pipeline
docker compose exec collector python -m collector.scheduler --run lens_sync
docker compose exec collector python -m collector.scheduler --run stroymonitoring_sync
docker compose exec collector python -m collector.scheduler --run genplan
docker compose exec collector python -m collector.scheduler --run ogh_disruption
docker compose exec collector python -m collector.scheduler --run vector_stroy_url_222

docker compose exec collector python -m collector.scheduler --run-all
```

## Podklyuchenie k lokalnoy BD

```
Host:     localhost
Port:     5432
Database: monitor
User:     monitor
Password: monitor
```

Skhemy: `data_mos`, `lens`, `stroymonitoring`, `genplan`, `collector` (logi zapuskov).

### Stroymonitoring (web_geo)

Istochnik: `WEB_GEO_DB_*` → `public.boundaries_aip`. Priemnik: `stroymonitoring.boundaries_aip` (polnaya perezagruzka). Konteyner `collector` dolzhen imet dostup k hostu `WEB_GEO_DB_HOST:5432`.

```bash
# V korne proekta v faile .env (ne tolko .env.example):
# WEB_GEO_DB_PASSWORD=ваш_пароль
docker compose up -d collector   # perечitat env posle izmeneniya .env

docker compose exec collector python -m collector.scheduler --run stroymonitoring_sync
# ili oba shaga kak v 04:00:
docker compose exec collector python -m collector.scheduler --run lens_pipeline
```

## Proverka logov zadach

```sql
SELECT * FROM collector.job_runs ORDER BY started_at DESC LIMIT 20;
```

## VPS Deploy

```bash
apt-get update && apt-get install -y ca-certificates curl gnupg git
# ... Docker install (see previous README section) ...
cd /opt/monitor
cp .env.example .env
docker compose up -d --build
docker compose exec -T db psql -U monitor -d monitor < sql/06_data_mos_extra_tables.sql
docker compose exec -T db psql -U monitor -d monitor < sql/08_reports_geom.sql
docker compose exec -T db psql -U monitor -d monitor < sql/10_genplan_multi_tables.sql
docker compose exec -T db psql -U monitor -d monitor < sql/14_lens_stroymonitoring_purge_functions.sql
```

## Genplan (`jsons_genplan/`)

JSON-fayly v papke `jsons_genplan/` (v korne proekta, v Docker — `/app/jsons_genplan`). Tip opredelyaetsya po strukture, ne po imeni fayla:

| Struktura | Tablitsa | Geometriya |
|-----------|----------|------------|
| est `wkt` | `genplan.order` | `geom` iz WKT |
| est `lat` i `lng` | `genplan.photo_meta` | `geom` = tochka; `lat`/`lng` v kolonkakh |
| est `uuids` (massiv) | `genplan.uuid_area` | odna stroka na kazhdyy uuid |
| bez koordinat | `genplan.upload` | bez `geom` |

Ostalnye klyuchi JSON → dinamicheskie kolonki (snake_case). Obraztsy `order.json`, `photo_meta.json`, `upload.json`, `uuid_area.json` posle importa ne udalyayutsya.

## SSH tunnel to DB

```bash
ssh -i <path_to_private_key> -L 5432:127.0.0.1:5432 root@77.222.63.161
```

## Update / rollback

```bash
cd /opt/monitor
git pull
docker compose up -d --build
docker compose exec -T db psql -U monitor -d monitor < sql/06_data_mos_extra_tables.sql
docker compose exec -T db psql -U monitor -d monitor < sql/08_reports_geom.sql
docker compose exec -T db psql -U monitor -d monitor < sql/05_data_mos_purge_functions.sql
docker compose exec -T db psql -U monitor -d monitor < sql/14_lens_stroymonitoring_purge_functions.sql
docker compose exec collector python -m collector.scheduler --run data_mos
```

## Checklist posle deploy

```bash
docker compose ps
docker compose exec collector python -m collector.scheduler --run data_mos_1498
docker compose logs collector --tail 200
```

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'data_mos' AND table_name LIKE 'items_%' ORDER BY 1;

SELECT count(*) FROM data_mos.items_1498;
SELECT count(*) FROM data_mos.items_2855;
SELECT count(*) FROM stroymonitoring.boundaries_aip;
```

Proverte, chto port 5432 nedostupen izvne bez SSH-tunnelya.
