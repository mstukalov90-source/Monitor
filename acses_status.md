# MONITOR — статус доступности функций

**Сервер:** `172.21.198.219` (RED OS 8.0.2)  
**Путь проекта:** `/opt/monitor`  
**Дата проверки:** 2026-06-23 (MSK)  
**Предыдущий сервер:** `77.222.63.161` (MONITOR остановлен не был)

---

## Инфраструктура

| Компонент | Статус | Детали |
|-----------|--------|--------|
| Диск `/` | OK | 489 GB всего, ~13 GB занято, **~457 GB свободно** (3%) |
| `monitor-db` | OK | PostGIS 16-3.4, healthy, порт `5432` |
| `monitor-api` | OK | Uvicorn, порт `8000` |
| `monitor-collector` | OK | APScheduler, cron 03:00 / 04:00 / 06:00 MSK |
| API с Mac | OK | `curl http://172.21.198.219:8000/health` → `{"status":"ok"}` |
| Firewall | Не настроен | `firewalld` inactive; порты `5432`, `8000` на `0.0.0.0` |

---

## M2M API (genplan + полевые фото)

| Функция | Endpoint | Статус | Проверка |
|---------|----------|--------|----------|
| Health | `GET /health` | **OK** | Без авторизации, `{"status":"ok"}` |
| Photo meta ingest | `PUT /api/photos/meta/{uuid}` | **OK** | С `Authorization: Bearer <MONITOR_API_KEY>` → `201 created` / `200 updated`; запись в `genplan.photo_meta` |
| Photo meta auth | без ключа | **OK** | `401 Missing or invalid Authorization header` |
| Photo meta auth | неверный ключ | **OK** | `401 Invalid API key` |
| UUID ingest | `PUT /api/uuids/{uuid}` | **OK** | Первая отправка → `201`; повтор → `409 uuid already exists`; запись в `genplan.uuid_api` |
| Полевые фото (Android) | `POST /api/mggtfield/photos` | **OK** | Multipart `file` → `201`, файл в `/opt/monitor/mggtfield_photo/` |
| Полевые фото | без файла | **OK** | `422 Field required` (валидация) |

**Base URL для коллег:** `http://172.21.198.219:8000`  
**Ключ API:** без изменений (из `.env` старого сервера)

### Данные API в БД (на момент проверки)

| Таблица | Строк |
|---------|------:|
| `genplan.photo_meta` | 219 814 |
| `genplan.uuid_api` | 8 |
| `lens.reports` | 141 |
| `stroymonitoring.boundaries_aip` | 1 333 |

---

## ETL Jobs — планировщик

### Cron (автоматические)

| Время MSK | Job | Статус | Комментарий |
|-----------|-----|--------|-------------|
| 03:00 | `data_mos` | **OK** | Цепочка 8 экспортов + `ogh_disruption`; проверены `data_mos_2941`, `data_mos_2855` — success |
| 03:00 | `data_mos_2855` | **OK** | 3204 features, purge, geom split |
| 03:00 | `data_mos_2941` | **OK** | 1980 features, purge 561 |
| 03:00 | `data_mos_62461` | **OK*** | Последний успешный прогон 23.06 03:00 (данные с миграции) |
| 03:00 | `data_mos_62501` | **OK*** | То же |
| 03:00 | `data_mos_1498` | **OK*** | То же |
| 03:00 | `data_mos_1500` | **OK*** | То же |
| 03:00 | `data_mos_2386` | **OK*** | То же |
| 03:00 | `data_mos_62441` | **OK*** | То же |
| 03:00 | `ogh_disruption` | **OK** | Skip если нет `mggt_dgn/mggt_dgn.geojson` |
| 04:00 | `lens_pipeline` | **OK** | `lens_sync` → `stroymonitoring_sync` |
| 04:00 | `lens_sync` | **OK** | 11 таблиц, ~1.19M строк, purge 1769 reports |
| 04:00 | `stroymonitoring_sync` | **OK** | 1921 rows, purge 588 |
| 06:00 | `vector_stroy_url_222` | **OK** | Skip если нет `url_222_wgs.geojson` в корне проекта |

\* Остальные `data_mos_*` не перезапускались вручную в этой сессии, но успешно отработали на старом сервере 23.06 03:00 MSK; инфраструктура и `data_mos_2855`/`2941` подтверждены на новом.

### Ручные jobs

| Job | Статус | Комментарий |
|-----|--------|-------------|
| `genplan` | **OK** | Импорт JSON из `jsons_genplan/`; сейчас нет файлов → skip |
| `genplan_upload` | **OK** | Загрузка в MSI Holes из `photo_to_upload/`; сейчас нет новых фото |
| `genplan_fetch_uploaded` | **OK** | 66 UUID → meta upsert из MSI Holes `GET /api/photos/meta/{uuid}` |
| `genplan_download` | **OK** | 118 фото matched, все уже на диске в `downloaded_photo/` |
| `genplan_fetch` | **FAIL** | MSI Holes `POST /api/spatial_search` → **HTTP 404** |
| `genplan_pipeline` | **FAIL** | Падает на `genplan_fetch` (404 spatial_search) |
| `genplan_upload_pipeline` | **Частично** | `genplan_upload` + `genplan_fetch_uploaded` + `genplan` — upload skip, fetch_uploaded OK; полный pipeline без spatial_search работает через upload-ветку |

---

## Внешние зависимости

| Ресурс | Хост | Статус | Назначение |
|--------|------|--------|------------|
| SPS (lens) | `172.16.206.170:5432` | **OK** | `lens_sync` |
| web_geo | `172.21.198.149:5432` | **OK** | `stroymonitoring_sync` |
| MSI Holes API | `https://m2m.msi-holes.cxm.dev` | **Частично** | `GET /api/photos/meta/{uuid}` — OK; `POST /api/spatial_search` — **404** |
| MSI Holes OAuth | `https://id.cxm.dev/oauth2/token` | **OK** | Токен для MSI Holes (используется в fetch_uploaded) |
| data.mos.ru | `https://apidata.mos.ru` | **OK** | HTTP 401 без ключа — сервер доступен; ключ в `.env` |

---

## Сетевая доступность

Проверка 2026-06-23: зонд со **старого** сервера (`77.222.63.161`) + исходящие тесты с **нового** (`172.21.198.219`).

### Старый → новый (недоступен)

Старый VPS в интернете, новый — только во внутренней сети `172.21.198.0/24` (интерфейс `ens192`, публичного IP нет).

| Проверка с `77.222.63.161` | Результат |
|----------------------------|-----------|
| Ping `172.21.198.219` | **FAIL** — 100% packet loss |
| TCP 22, 5432, 8000, 80, 443 | **FAIL** — timeout |
| `curl http://172.21.198.219:8000/health` | **FAIL** — недоступен |

Со старого сервера **нельзя** проверить входящие порты нового — маршрута нет. Это ожидаемо; миграция шла через локальную машину.

### Исходящие доступы: старый vs новый

| Ресурс | Старый `77.222.63.161` | Новый `172.21.198.219` |
|--------|------------------------|------------------------|
| SPS `172.16.206.170:5432` | **FAIL** (timeout) | **OK** — PG auth OK |
| web_geo `172.21.198.149:5432` | **FAIL** (timeout) | **OK** — PG auth OK |
| Старый MONITOR `77.222.63.161:5432` / `:8000` | — | **OK** |
| GitHub `:443` | OK | OK |
| data.mos.ru `:443` | OK | OK |
| MSI Holes `:443` | OK | OK |
| Новый MONITOR `172.21.198.219` | **FAIL** | — |

На **новом** сервере `lens_sync` и `stroymonitoring_sync` работают — он в корпоративной сети вместе с SPS и web_geo. На **старом** VPS эти БД были недоступны (`Connection timed out` в `job_runs`).

### Входящие доступы к новому серверу

| Порт | Сервис | Интерфейс |
|------|--------|-----------|
| 22 | SSH | `0.0.0.0` |
| 5432 | PostgreSQL (`monitor-db`) | `0.0.0.0` |
| 8000 | MONITOR API | `0.0.0.0` |

| Откуда | API `:8000` | PG `:5432` | Комментарий |
|--------|-------------|------------|-------------|
| Внутренняя сеть `172.21.x` / VPN | OK | OK* | основной сценарий |
| Публичный интернет | **Нет** | **Нет** | нет публичного IP у нового сервера |
| Старый VPS `77.222.63.161` | **Нет** | **Нет** | другая сеть, маршрута нет |

\* PostgreSQL с Mac/внешних клиентов не проверялся; порт слушает на всех интерфейсах.

**Важно для коллег:** адрес `http://172.21.198.219:8000` доступен только из внутренней сети или VPN — в отличие от старого публичного `http://77.222.63.161:8000`.

---

## Схемы БД

| Схема | Таблиц | Статус |
|-------|-------:|--------|
| `data_mos` | 20 | OK |
| `lens` | 11 | OK |
| `genplan` | 5 | OK |
| `stroymonitoring` | 1 | OK |
| `collector` | 1 | OK (`job_runs`) |
| `crm` | 7 | OK |
| `odh_export` | 4 | OK |
| `vector_stroy` | 1 | OK |

---

## Файлы и каталоги на диске

| Путь | Статус | Комментарий |
|------|--------|-------------|
| `/opt/monitor/.env` | OK | `MONITOR_API_PUBLIC_BASE_URL=http://172.21.198.219:8000` |
| `genplan api/msi-holes-backend.client.json` | OK | OAuth credentials |
| `mggtfield_photo/` | OK | 5+ файлов, upload проверен |
| `downloaded_photo/` | OK | 334 файла |
| `jsons_genplan/` | Пусто | `genplan` job ждёт JSON |
| `photo_to_upload/` | Пусто | `genplan_upload` ждёт фото |
| `mggt_dgn/mggt_dgn.geojson` | Нет | `ogh_disruption` skip |
| `url_222_wgs.geojson` | Нет | `vector_stroy_url_222` skip |

---

## Известные проблемы

### 1. `genplan_fetch` / `genplan_pipeline` — MSI Holes 404

```
Client error '404 Not Found' for url 'https://m2m.msi-holes.cxm.dev/api/spatial_search'
```

Проблема **не связана с миграцией** — та же ошибка была на старом сервере. Push-канал через M2M API (`PUT /api/photos/meta/{uuid}`) и `genplan_fetch_uploaded` работают.

**Обходной путь:** использовать M2M API коллег + `genplan_fetch_uploaded` для загруженных фото.

### 2. Исторические `DiskFull` в `job_runs`

Записи 14:14 MSK — до расширения диска с 13 GB до 489 GB. После расширения все повторные прогоны — success.

### 3. Firewall не настроен

Порты `5432` и `8000` открыты для всех интерфейсов. Рекомендуется ограничить доверенными IP.

### 4. Старый сервер

`77.222.63.161` — MONITOR ещё может быть запущен параллельно. Контейнеры `lens-report*` сняты (`docker compose down` в `/opt/lens-report`). После cutover: `docker compose stop` в `/opt/monitor`.

---

## Сводка: что работает / что нет

| Категория | Работает | Не работает |
|-----------|----------|-------------|
| **API** | health, photo meta, uuid, mggtfield upload | — |
| **Cron ETL** | data_mos, ogh_disruption, lens_pipeline, vector_stroy_url_222 | — |
| **Sync** | lens_sync, stroymonitoring_sync | — |
| **Genplan manual** | genplan, genplan_upload, genplan_fetch_uploaded, genplan_download | genplan_fetch, genplan_pipeline |
| **Инфраструктура** | Docker, БД, диск, сеть к SPS/web_geo | firewall (не настроен); API только из внутренней сети/VPN |

---

## Команды для повторной проверки

```bash
# API
curl -s http://172.21.198.219:8000/health

# Контейнеры
ssh root@172.21.198.219 'cd /opt/monitor && docker-compose ps'

# Последние jobs
ssh root@172.21.198.219 'cd /opt/monitor && docker-compose exec -T db psql -U monitor -d monitor -c "
SELECT job_name, status, left(message,60), started_at AT TIME ZONE '\''Europe/Moscow'\''
FROM collector.job_runs ORDER BY started_at DESC LIMIT 15;"'

# Ручной запуск job
ssh root@172.21.198.219 'cd /opt/monitor && docker-compose exec collector python -m collector.scheduler --run lens_sync'

# Сетевая доступность с нового сервера
ssh root@172.21.198.219 'timeout 3 bash -c "echo >/dev/tcp/172.16.206.170/5432" && echo SPS:OK || echo SPS:FAIL'
ssh root@172.21.198.219 'curl -s -o /dev/null -w "%{http_code}" http://77.222.63.161:8000/health'
```

---

## Cutover для потребителей

| Параметр | Было | Стало |
|----------|------|-------|
| API Base URL | `http://77.222.63.161:8000` | `http://172.21.198.219:8000` |
| PostgreSQL host | `77.222.63.161` | `172.21.198.219` |
| PostgreSQL port | `5432` | `5432` |
| API key | — | без изменений |
