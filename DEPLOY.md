# Деплой MONITOR

**Основной прод-сервер:** `172.21.198.219` (`LEN-MOSTRRAB-DCR-01P`, RED OS)  
**Путь:** `/opt/monitor`  
**SSH:** `ssh root@172.21.198.219`  

**Публичный M2M (смежники):** `https://monitor-crm.mggt.ru`  
**Тест (SWEB, не прод):** `http://77.222.63.161:8000`  

Конфиг сервера и переезд: [`mggt_server/SERVER.md`](mggt_server/SERVER.md), [`mggt_server/MIGRATION.md`](mggt_server/MIGRATION.md), пакет для коллег: [`mggt_server/API/`](mggt_server/API/).

Инструкция ниже — развёртывание/обновление стека Docker и БД. На проде также работают nginx (WebCRM `:80`), `monitor-webcrm` (`:8080` localhost), firewalld.

## Требования

- Прод: RED OS / доступ `root@172.21.198.219` (или тестовый VPS с Docker)
- Docker Engine и плагин Docker Compose (`docker compose`)
- Git и доступ к репозиторию: `git@github.com:mstukalov90-source/Monitor.git`
- На локальной машине (при переносе БД): запущенный стек MONITOR с данными

Рекомендуемый путь на сервере: `/opt/monitor`.

## 1. Клонирование или обновление кода

Первичная установка:

```bash
cd /opt
git clone git@github.com:mstukalov90-source/Monitor.git monitor
cd /opt/monitor
```

Обновление существующей копии:

```bash
cd /opt/monitor
git pull origin main
```

## 2. Настройка окружения

```bash
cd /opt/monitor
cp .env.example .env
nano .env   # или другой редактор
```

Обязательно задайте:

- `POSTGRES_PASSWORD` — длинный случайный пароль
- `REMOTE_DB_*` — доступ к SPS для `lens_sync`
- `WEB_GEO_DB_PASSWORD` — для `stroymonitoring_sync`
- `DATA_MOS_API_KEY` — при необходимости для data.mos.ru
- `MONITOR_API_KEY` — 256-битный API-ключ для M2M (64 hex)
- `MONITOR_API_PUBLIC_BASE_URL` — публичный адрес для смежников: `https://monitor-crm.mggt.ru`
- `MONITOR_API_PORT` — порт на хосте (по умолчанию `8000`)
- `MGGT_FIELD_PHOTO_DIR` — каталог полевых фото (`/opt/monitor/mggtfield_photo`)
- `MGGT_FIELD_PHOTO_MAX_BYTES` — лимит размера (по умолчанию `20971520`)

Сгенерировать ключ:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Пример в `.env` (прод):

```env
MONITOR_API_PUBLIC_BASE_URL=https://monitor-crm.mggt.ru
MONITOR_API_KEY=<64_hex_chars>
MONITOR_API_PORT=8000
```

Ключ передаётся коллегам отдельно (см. [`mggt_server/API/ONBOARDING.md`](mggt_server/API/ONBOARDING.md)). В git не коммитить. Файл `.env` не коммитить.

## 3. Запуск контейнеров

```bash
cd /opt/monitor
docker compose up -d --build
docker compose ps
```

Ожидаемые сервисы:

- `monitor-db` — PostGIS (порт `5432`; на проде — корпсеть `172.21.0.0/16`, не интернет)
- `monitor-collector` — планировщик ETL
- `monitor-api` — M2M HTTP API (порт `8000`; снаружи для смежников — через домен `:443` → nginx `:80`)

## 4. Перенос базы данных с локальной машины

Выполняется **на компьютере**, где уже есть рабочая БД с нужными данными.

### 4.1 Создать дамп

```bash
cd /path/to/MONITOR
docker compose exec -T db pg_dump -U monitor -d monitor -Fc --no-owner --no-acl -f /tmp/monitor_full.dump
docker cp monitor-db:/tmp/monitor_full.dump ./monitor_full.dump
```

### 4.2 Скопировать на прод

```bash
scp -i <path_to_ssh_key> ./monitor_full.dump root@172.21.198.219:/tmp/monitor_full.dump
```

### 4.3 Восстановить на прод

На проде initdb-скрипты Docker создают stub-схемы — для чистого restore предпочтительно пустая БД + PostGIS, затем `pg_restore` из файла в контейнере (см. [`mggt_server/STAGE_FINAL_RESYNC_REPORT.md`](mggt_server/STAGE_FINAL_RESYNC_REPORT.md)).

```bash
ssh root@172.21.198.219
cd /opt/monitor
docker cp /tmp/monitor_full.dump monitor-db:/tmp/monitor_full.dump
docker compose exec -T db pg_restore -U monitor -d monitor --no-owner --no-acl /tmp/monitor_full.dump
```

Пароль для подключения к БД — из `.env` на сервере (`POSTGRES_PASSWORD`).

## 5. Firewall (прод)

На `.219` используется **firewalld** (не ufw). Актуальные rich-rules: corp `172.21.0.0/16` → `80`/`8000`/`5432`; шлюз `192.168.1.217` → `80`/`8000`. PG в интернет не открывать. См. [`mggt_server/SERVER.md`](mggt_server/SERVER.md), [`mggt_server/firewall/server-firewalld.sh`](mggt_server/firewall/server-firewalld.sh).

```bash
firewall-cmd --list-rich-rules
```

## 6. Проверка после деплоя

```bash
cd /opt/monitor
docker compose ps
docker compose logs collector --tail 100
curl -sS http://127.0.0.1:8000/health
curl -sS https://monitor-crm.mggt.ru/health   # с хоста с интернетом / SWEB
```

Ручной запуск задач:

```bash
docker compose exec collector python -m collector.scheduler --run data_mos
docker compose exec collector python -m collector.scheduler --run lens_pipeline
docker compose exec collector python -m collector.scheduler --run genplan
```

Проверка в БД:

```bash
docker compose exec -T db psql -U monitor -d monitor -c "
SELECT schemaname, count(*) AS tables
FROM pg_tables
WHERE schemaname IN ('data_mos','lens','stroymonitoring','genplan','collector','crm')
GROUP BY schemaname
ORDER BY 1;
"

docker compose exec -T db psql -U monitor -d monitor -c "
SELECT job_name, status, rows_affected, started_at
FROM collector.job_runs
ORDER BY started_at DESC
LIMIT 10;
"
```

## 7. Подключение к БД

PostgreSQL на проде **не** для интернета. Доступ из корпсети / VPN (Android) или SSH-туннель.

| Параметр | Значение |
|----------|----------|
| Host | `172.21.198.219` |
| Port | `5432` |
| Database | `monitor` |
| User | `monitor` |
| Password | из `POSTGRES_PASSWORD` |

```
postgresql://monitor:<password>@172.21.198.219:5432/monitor
```

Туннель с Mac:

```bash
ssh -L 5432:127.0.0.1:5432 root@172.21.198.219
```

## 8. Обновление версии на сервере

```bash
cd /opt/monitor
git pull origin main
docker compose up -d --build
docker compose ps
```

При изменении схемы — миграции из `sql/` или dump/restore. На проде не гонять деструктивные WebCRM SQL (`28_cleanup_*`) вслепую.

## 9. Genplan M2M API (приём photo meta и uuid)

Коллеги отправляют данные на MONITOR в push-режиме:

- `PUT /api/photos/meta/{uuid}` — JSON meta → `genplan.photo_meta` (upsert)
- `PUT /api/uuids/{uuid}` — только uuid → `genplan.uuid_api` (insert-only, дубликат → 409)

**Прод Base URL:** `https://monitor-crm.mggt.ru` (HTTPS).  
Внутри корпсети / VPN также: `http://172.21.198.219:8000` или через nginx `:80`.

Документация для коллег:

- [`mggt_server/API/ONBOARDING.md`](mggt_server/API/ONBOARDING.md) — быстрый старт (актуальный пакет)
- [`mggt_server/API/monitor-api-doc.md`](mggt_server/API/monitor-api-doc.md)
- [`mggt_server/API/monitor-uuid-api-doc.md`](mggt_server/API/monitor-uuid-api-doc.md)
- [`mggt_server/API/monitor_client.py`](mggt_server/API/monitor_client.py)
- [`QGIS_api/`](QGIS_api/) — скачивание фото для QGIS (`GET /api/qgis/photos/...`)

### 9.1 Чеклист деплоя API

- [ ] Код на проде актуален (`git pull`)
- [ ] В `.env` задан `MONITOR_API_KEY` (без него API отвечает `503`)
- [ ] `MONITOR_API_PUBLIC_BASE_URL=https://monitor-crm.mggt.ru`
- [ ] Запущен `api`: `docker compose up -d --build api`
- [ ] Публичный `/health` ok: `curl -sS https://monitor-crm.mggt.ru/health`
- [ ] Проверен тестовый `PUT` uuid/meta

### 9.2 Запуск и миграция

```bash
cd /opt/monitor
docker compose exec -T db psql -U monitor -d monitor < sql/15_genplan_photo_meta_uuid.sql
docker compose exec -T db psql -U monitor -d monitor < sql/17_genplan_uuid_api.sql
docker compose up -d --build api
docker compose ps
```

### 9.3 Firewall

На проде — firewalld (см. §5). Снаружи смежники ходят на домен `:443`, не напрямую на `:8000` из интернета.

### 9.4 Проверка после деплоя

```bash
# с хоста с интернетом (например SWEB) или с Mac при рабочем ACL
curl -sS https://monitor-crm.mggt.ru/health
# {"status":"ok"}

curl -sS -w "\nHTTP %{http_code}\n" -X PUT \
  "https://monitor-crm.mggt.ru/api/photos/meta/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "status": "done",
    "lat": 55.78418187985141,
    "lng": 37.74234417284182,
    "image_name": "test.jpg"
  }'

# uuid-only
curl -sS -w "\nHTTP %{http_code}\n" -X PUT \
  "https://monitor-crm.mggt.ru/api/uuids/8d4c7a74-6c6f-4e53-a93d-9a6a7d5f2f21" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json"
```

На проде в БД:

```bash
ssh root@172.21.198.219 'cd /opt/monitor && docker compose exec -T db psql -U monitor -d monitor -c "
SELECT uuid, loaded_at FROM genplan.uuid_api ORDER BY loaded_at DESC LIMIT 5;
"'
```

### 9.5 Что передать коллегам

| Параметр | Значение |
|----------|----------|
| Base URL | `https://monitor-crm.mggt.ru` |
| Auth | `Authorization: Bearer <MONITOR_API_KEY>` |
| UUID only | `PUT /api/uuids/{uuid}` — без тела |
| Photo meta | `PUT /api/photos/meta/{uuid}` — JSON |
| QGIS photo download | `GET /api/qgis/photos/genplan/{uuid}`, `GET /api/qgis/photos/field/{filename}` |

Передаётся **только JSON meta**, не файл изображения (ingest). Скачивание бинарников для QGIS — пакет [`QGIS_api/`](QGIS_api/). Пакет ingest: [`mggt_server/API/`](mggt_server/API/).

### 9.6 Ограничения

- Снаружи — HTTPS на домене; прямой `:8000` с интернета на `.219` недоступен
- `GET` для чтения meta не реализован — endpoint'ы только **принимают** данные
- `PUT /api/uuids/{uuid}` — insert-only; дубликат → 409
- Тестовый стенд SWEB: `http://77.222.63.161:8000` — не для прода

## 10. Загрузка полевых фотографий (Android)

Мобильное приложение (VPN → корпсеть) отправляет JPEG/PNG через `POST /api/mggtfield/photos` на **`http://172.21.198.219:8000`**.

Документация: [`mggtfield-photo-api-doc.md`](mggtfield-photo-api-doc.md)

### 10.1 Чеклист деплоя

- [ ] Код на проде актуален
- [ ] `docker compose up -d --build api`
- [ ] Каталог:

```bash
mkdir -p /opt/monitor/mggtfield_photo
chmod 755 /opt/monitor/mggtfield_photo
```

- [ ] `MONITOR_API_KEY` задан
- [ ] С планшета (VPN) доступны `:8000` и при необходимости PG `:5432`

### 10.2 Проверка

```bash
curl -sS -w "\nHTTP %{http_code}\n" -X POST \
  "http://172.21.198.219:8000/api/mggtfield/photos" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json" \
  -F "file=@/path/to/test.jpg;type=image/jpeg;filename=test_upload.jpg"
```

### 10.3 Что передать Android-разработчику

| Параметр | Значение |
|----------|----------|
| Base URL | `http://172.21.198.219:8000` (VPN / корпсеть) |
| Метод | `POST /api/mggtfield/photos` |
| Auth | `Authorization: Bearer <MONITOR_API_KEY>` |
| Формат | `multipart/form-data`, поле `file` |
| Документация | `mggtfield-photo-api-doc.md` |

## Расписание задач

| Время (MSK) | Задача | Описание |
|-------------|--------|----------|
| 03:00 | `data_mos` | 8 экспортов data.mos.ru |
| 04:00 | `lens_pipeline` | `lens_sync` + `stroymonitoring_sync` |
| 06:00 | `vector_stroy_url_222` | fetch map221/rs_2022 → `vector_stroy.url_222` |

Токен vector.mka.mos.ru: `Vector_py/token.md` на сервере или `VECTOR_MKA_TOKEN`. Если сервер не видит vector.mka — fetch локально, затем scp `url_222_wgs.geojson` на `172.21.198.219`.

`genplan_pipeline` — **только ручной** запуск:

```bash
# В .env: GENPLAN_SEARCH_RADIUS_M=20000, GENPLAN_FETCH_META_LIMIT=0, MSI_HOLES_*
docker compose exec collector python -m collector.scheduler --run genplan_pipeline
```

Полный прогон при ~20k UUID может занять **час и более** (последовательные запросы meta).

Подробнее о сервисах и таблицах — в [README.md](README.md).
