# MONITOR - avtomaticheskiy sborshik dannykh

Docker-okruzhenie s PostGIS i planirovshchikom ETL-zadach.

## Raspisanie (Europe/Moscow)

| Vremya | Zadacha | Opisanie |
|-------|--------|----------|
| 03:00 | `data_mos` | Zapusk `data_mos_export.py`, zagruzka `Data_mos_export.geojson` v `data_mos.items`, udalenie `.geojson` i `.gpkg` |
| 04:00 | `lens_sync` | Kopirovanie tablits iz `public` udalennoy BD `sps` v lokalnuyu skhemu `lens` |
| 05:00 | `genplan` | Import `response_*.json` v `genplan.responses`, udalenie obrabotannykh faylov |

## Bystryy start

```bash
cp .env.example .env
# pri neobkhodimosti otredaktiruyte .env

docker compose up -d --build
```

## Ruchnoy zapusk zadach

```bash
# odna zadacha
docker compose exec collector python -m collector.scheduler --run data_mos
docker compose exec collector python -m collector.scheduler --run lens_sync
docker compose exec collector python -m collector.scheduler --run genplan

# vse zadachi podryad
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
# 1) Ustanovka Docker + Compose plugin
apt-get update
apt-get install -y ca-certificates curl gnupg git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 2) Klonirovanie proekta
cd /opt
git clone git@github.com:mstukalov90-source/Monitor.git monitor
cd /opt/monitor

# 3) Nastroyka okruzheniya
cp .env.example .env
# otredaktiruyte: POSTGRES_PASSWORD, DATA_MOS_API_KEY, REMOTE_DB_*

# 4) Zapusk
docker compose up -d --build
```

## SSH tunnel to DB

PostgreSQL ne otkryt naruzhu napryamuyu: v compose port privyazan k `127.0.0.1`.

```bash
ssh -i <path_to_private_key> -L 5432:127.0.0.1:5432 root@77.222.63.161
```

Posle etogo podklyuchaytes k BD kak k `localhost:5432` s lokalnoy mashiny.

## Update / rollback

```bash
# update
cd /opt/monitor
git pull
docker compose up -d --build

# check
docker compose ps
docker compose logs collector --tail 100

# rollback: checkout previous commit
PREV=$(git rev-parse HEAD~1)
git checkout "$PREV"
docker compose up -d --build
```

## Checklist posle deploy

```bash
# containers
docker compose ps

# manual run
docker compose exec collector python -m collector.scheduler --run data_mos
docker compose exec collector python -m collector.scheduler --run lens_sync
docker compose exec collector python -m collector.scheduler --run genplan

# logs
docker compose logs collector --tail 200
```

```sql
SELECT * FROM collector.job_runs ORDER BY started_at DESC LIMIT 20;
SELECT count(*) FROM data_mos.items;
SELECT count(*) FROM genplan.responses;
```

Proverte takzhe, chto port 5432 nedostupen izvne bez SSH-tunnelya.
