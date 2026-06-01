# MONITOR - avtomaticheskiy sborshik dannykh

Docker-okruzhenie s PostGIS i planirovshchikom ETL-zadach.

## Raspisanie (Europe/Moscow)

| Vremya | Zadacha | Opisanie |
|-------|--------|----------|
| 03:00 | `data_mos` | Vse 8 eksportov `data_mos_export_*.py` podryad → `data_mos.items_<id>` |
| 04:00 | `lens_sync` | Kopirovanie tablits iz `public` udalennoy BD `sps` v lokalnuyu skhemu `lens` |
| 05:00 | `genplan` | Import `response_*.json` v `genplan.responses`, udalenie obrabotannykh faylov |

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

```bash
docker compose exec -T db psql -U monitor -d monitor < sql/05_data_mos_purge_functions.sql
```

## Bystryy start

```bash
cp .env.example .env
docker compose up -d --build
```

Na sushchestvuyushchey BD primenite migratsii (06 — bez DROP, bezopasno):

```bash
docker compose exec -T db psql -U monitor -d monitor < sql/06_data_mos_extra_tables.sql
docker compose exec collector python -m collector.scheduler --run data_mos
```

Dlya polnogo peresozdaniya pervykh chetyrekh tablits (DROP dannykh): `sql/04_data_mos_dynamic_tables.sql`.

## Ruchnoy zapusk zadach

```bash
# vse 8 eksportov podryad
docker compose exec collector python -m collector.scheduler --run data_mos

# odin servis
docker compose exec collector python -m collector.scheduler --run data_mos_1498

# drugie zadachi
docker compose exec collector python -m collector.scheduler --run lens_sync
docker compose exec collector python -m collector.scheduler --run genplan

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

Skhemy: `data_mos`, `lens`, `genplan`, `collector` (logi zapuskov).

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
docker compose exec -T db psql -U monitor -d monitor < sql/05_data_mos_purge_functions.sql
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
```

Proverte, chto port 5432 nedostupen izvne bez SSH-tunnelya.
