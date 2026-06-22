# MONITOR - avtomaticheskiy sborshik dannykh

Docker-okruzhenie s PostGIS i planirovshchikom ETL-zadach.

## Raspisanie (Europe/Moscow)

| Vremya | Zadacha | Opisanie |
|-------|--------|----------|
| 03:00 | `data_mos` | Vse 8 eksportov `data_mos_export_*.py` → `data_mos.items_<id>`; zatem `ogh_disruption`: esli est `mggt_dgn/mggt_dgn.geojson` — upsert v `odh_export."ogh-disruption"` po `(source_json, lon, lat)` — slivanie tolko pri sovpadenii koordinat, udalenie fayla |
| 04:00 | `lens_pipeline` | `lens_sync` (SPS → `lens`), zatem `stroymonitoring_sync` (web_geo → `stroymonitoring`) |
| 06:00 | `vector_stroy_url_222` | Esli v korne proekta est `url_222_wgs.geojson` — upsert v `vector_stroy.url_222` po `uuid`, zatem udalenie fayla; inache propusk |

`genplan_pipeline` (`genplan_fetch` + import) — **tolko ruchnoy zapusk**: `--run genplan_pipeline`

`genplan_upload` — zagruzka fotografiy iz `photo_to_upload/` v MSI Holes API (`POST /api/upload`); otvet zapisyvaetsya v `genplan.uploaded_photo`. Posle uspekha fayl peremeshchaetsya v `photo_uploaded/`. Zapusk: `--run genplan_upload` ili tsepochka `--run genplan_upload_pipeline` (upload → `genplan_fetch_uploaded` → import).

`genplan_fetch_uploaded` — po UUID iz `genplan.uploaded_photo` zabiraet meta iz MSI Holes (`GET /api/photos/meta/{uuid}`) i upsert v `genplan.photo_meta`. Ruchnoy zapusk: `--run genplan_fetch_uploaded`.

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
docker compose exec collector python -m collector.scheduler --run genplan_pipeline
docker compose exec collector python -m collector.scheduler --run genplan_fetch
docker compose exec collector python -m collector.scheduler --run genplan_fetch_uploaded
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
# Zapolnit .env: MSI_HOLES_CLIENT_ID/SECRET (ili skopirovat genplan api/msi-holes-backend.client.json)
docker compose up -d --build
docker compose exec -T db psql -U monitor -d monitor < sql/06_data_mos_extra_tables.sql
docker compose exec -T db psql -U monitor -d monitor < sql/08_reports_geom.sql
docker compose exec -T db psql -U monitor -d monitor < sql/10_genplan_multi_tables.sql
docker compose exec -T db psql -U monitor -d monitor < sql/14_lens_stroymonitoring_purge_functions.sql
docker compose exec -T db psql -U monitor -d monitor < sql/15_genplan_photo_meta_uuid.sql
docker compose exec -T db psql -U monitor -d monitor < sql/16_genplan_uploaded_photo.sql
```

MSI Holes credentials **ne v git** (`.gitignore`: `genplan api/msi-holes-backend.client.json`). Na VPS — libo fayl v `genplan api/`, libo peremennye v `.env`.

## Genplan (`jsons_genplan/`)

V 05:00 cron **ne zapuskaetsya** — tolko vruchnuyu: `--run genplan_pipeline`. Shagi: `genplan_fetch` zabiraet dannye iz MSI Holes API (`POST /api/spatial_search`, `GET /api/photos/meta/{uuid}`), zatem `genplan` importiruet JSON v BD.

Peremennye okruzheniya (v `.env`):

```
MSI_HOLES_CLIENT_ID=
MSI_HOLES_CLIENT_SECRET=
MSI_HOLES_BASE_URL=https://m2m.msi-holes.cxm.dev
MSI_HOLES_TOKEN_ENDPOINT=https://id.cxm.dev/oauth2/token
GENPLAN_SEARCH_LAT=55.7558
GENPLAN_SEARCH_LNG=37.6173
GENPLAN_SEARCH_RADIUS_M=20000
```

Po umolchaniyu poisk vypolnyaetsya v radius **20 km** ot tsentra Moskvy (`GENPLAN_SEARCH_RADIUS_M=20000`). Polnyy progon pri bolshom chisle UUID mozhet zanyat desyatki minut i dolshe; povtornyy `genplan_pipeline` dozagruzhaet tolko novye UUID.

JSON-fayly v papke `jsons_genplan/` (v korne proekta, v Docker — `/app/jsons_genplan`). Tip opredelyaetsya po strukture, ne po imeni fayla:

| Struktura | Tablitsa | Geometriya |
|-----------|----------|------------|
| est `wkt` | `genplan.order` | `geom` iz WKT |
| est `lat` i `lng` | `genplan.photo_meta` | `geom` = tochka; `lat`/`lng` v kolonkakh |
| est `uuids` (massiv) | `genplan.uuid_area` | odna stroka na kazhdyy uuid |
| bez koordinat | `genplan.upload` | bez `geom` |

Ostalnye klyuchi JSON → dinamicheskie kolonki (snake_case). Obraztsy `order.json`, `photo_meta.json`, `upload.json`, `uuid_area.json` posle importa ne udalyayutsya.

### Zagruzka fotografiy v Genplan (`photo_to_upload/`)

Ruchnoy job `genplan_upload` otpravlyaet snimki v MSI Holes API. Metadannye formiruyutsya avtomaticheski:

| Pole | Istochnik |
|------|-----------|
| `date` | EXIF `DateTimeOriginal` / `DateTime`, inache data iz imeni fayla (`YYYY-MM-DD`) |
| `lat`, `lng` | EXIF GPS |
| `azimuth_deg` | EXIF `GPSImgDirection` |

Esli dannykh net — pole ne otpravlyaetsya v API i v BD zapisyvaetsya `NULL`.

```bash
# Polozhit .jpg / .png v photo_to_upload/
docker compose exec collector python -m collector.scheduler --run genplan_upload

# Tolko meta dlya uzhe otpravlennykh foto (UUID iz genplan.uploaded_photo)
docker compose exec collector python -m collector.scheduler --run genplan_fetch_uploaded

# Upload + poluchenie meta iz MSI Holes + import ostalnykh JSON
docker compose exec collector python -m collector.scheduler --run genplan_upload_pipeline
```

Tsepochka `genplan_upload_pipeline`: `genplan_upload` → `genplan_fetch_uploaded` → `genplan`. Meta dlya otpravlennykh foto beretsya po UUID iz `uploaded_photo`, a ne cherez `spatial_search` (`genplan_fetch`).

Peremennaya `GENPLAN_FETCH_UPLOADED_LIMIT` (0 = bez limita) ogranicivaet chislo UUID za odin progon.

Migratsiya tablitsy `genplan.uploaded_photo`:

```bash
docker compose exec -T db psql -U monitor -d monitor < sql/16_genplan_uploaded_photo.sql
```

Proverka:

```sql
SELECT file_name, uuid, name, upload_at, lat, lng, azimuth_deg, loaded_at
FROM genplan.uploaded_photo
ORDER BY loaded_at DESC
LIMIT 10;

SELECT up.uuid, up.file_name, pm.status, pm.disruption, pm.loaded_at
FROM genplan.uploaded_photo up
LEFT JOIN genplan.photo_meta pm ON pm.uuid = up.uuid
ORDER BY up.loaded_at DESC
LIMIT 10;
```

## Genplan M2M API (priem meta)

Otdelnyy servis `api` prinimaet JSON metadannykh fotografiy ot kolleg (push). Dannye sohranyayutsya v `genplan.photo_meta` s upsert po `uuid`.

```bash
docker compose up -d --build api
curl -s http://localhost:8000/health
```

Peremennye v `.env`:

```
MONITOR_API_PUBLIC_BASE_URL=http://77.222.63.161:8000
MONITOR_API_KEY=<64_hex_chars>   # 256 bit: python3 -c "import secrets; print(secrets.token_hex(32))"
MONITOR_API_KEYS=                # opcionalno: key1,key2
MONITOR_API_PORT=8000
```

Kollegam peredat Base URL `http://77.222.63.161:8000` i vydannyj API-klyuch. Otkryt port 8000 v firewall tolko dlya IP kolleg.

Endpoint: `PUT /api/photos/meta/{uuid}`, zagolovok `Authorization: Bearer <MONITOR_API_KEY>`.

Endpoint UUID (tolko identifikator): `PUT /api/uuids/{uuid}` → `genplan.uuid_api` (insert-only, dublikat → 409).

Dokumentatsiya dlya kolleg: `genplan api/ONBOARDING.md`, `genplan api/monitor-api-doc.md`, `genplan api/monitor-uuid-api-doc.md`, primer klienta `genplan api/monitor_client.py`.

Migratsiya uuid dlya sushchestvuyushchey BD:

```bash
docker compose exec -T db psql -U monitor -d monitor < sql/15_genplan_photo_meta_uuid.sql
docker compose exec -T db psql -U monitor -d monitor < sql/16_genplan_uploaded_photo.sql
docker compose exec -T db psql -U monitor -d monitor < sql/17_genplan_uuid_api.sql
```

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
docker compose exec -T db psql -U monitor -d monitor < sql/15_genplan_photo_meta_uuid.sql
docker compose exec -T db psql -U monitor -d monitor < sql/16_genplan_uploaded_photo.sql
docker compose exec collector python -m collector.scheduler --run data_mos
```

## Checklist posle deploy

```bash
docker compose ps
docker compose exec collector python -m collector.scheduler --run data_mos_1498
docker compose logs collector --tail 200

# MONITOR M2M API (esli podnyat servis api)
curl -s http://localhost:8000/health

# Genplan upload (smoke test, opcionalno)
mkdir -p photo_to_upload
# polozhit odin testovyy .jpg v photo_to_upload/
docker compose exec collector python -m collector.scheduler --run genplan_upload
```

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'data_mos' AND table_name LIKE 'items_%' ORDER BY 1;

SELECT count(*) FROM data_mos.items_1498;
SELECT count(*) FROM data_mos.items_2855;
SELECT count(*) FROM stroymonitoring.boundaries_aip;

-- Genplan: tablitsy i poslednie zagruzki
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'genplan' ORDER BY 1;

SELECT file_name, uuid, name, upload_at, lat, lng, loaded_at
FROM genplan.uploaded_photo
ORDER BY loaded_at DESC
LIMIT 5;

SELECT job_name, status, message, started_at
FROM collector.job_runs
WHERE job_name IN ('genplan_upload', 'genplan_fetch_uploaded', 'genplan_fetch', 'genplan')
ORDER BY started_at DESC
LIMIT 10;
```

Proverte:
- port 5432 nedostupen izvne bez SSH-tunnelya;
- `genplan api/msi-holes-backend.client.json` ili `MSI_HOLES_*` v `.env` na meste;
- posle uspeshnogo `genplan_upload` fayl peremeshchen v `photo_uploaded/`.
