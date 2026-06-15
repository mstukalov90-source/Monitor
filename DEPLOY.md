# Деплой MONITOR на VPS

Инструкция по развёртыванию актуальной версии сборщика на сервере и переносу базы данных с локальной машины.

## Требования

- VPS с Ubuntu/Debian, доступ по SSH (`root` или sudo-пользователь)
- Docker Engine и плагин Docker Compose (`docker compose`)
- Git и доступ к репозиторию: `git@github.com:mstukalov90-source/Monitor.git`
- На локальной машине: запущенный стек MONITOR с актуальными данными в БД

Рекомендуемый путь на сервере: `/opt/monitor`.

## 1. Клонирование или обновление кода на VPS

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
- `MONITOR_API_KEY` — 256-битный API-ключ для M2M-приёма photo meta (64 hex-символа)
- `MONITOR_API_PUBLIC_BASE_URL` — публичный адрес API для коллег (без домена: `http://<IP_VPS>:8000`)
- `MONITOR_API_PORT` — порт на хосте (по умолчанию `8000`)

Сгенерировать ключ:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Пример в `.env`:

```env
MONITOR_API_PUBLIC_BASE_URL=http://77.222.63.161:8000
MONITOR_API_KEY=<64_hex_chars>
MONITOR_API_PORT=8000
```

Ключ передаётся коллегам отдельно (см. `genplan api/ONBOARDING.md`). В git не коммитить.

Файл `.env` не коммитить в git.

## 3. Запуск контейнеров

```bash
cd /opt/monitor
docker compose up -d --build
docker compose ps
```

Ожидаемые сервисы:

- `monitor-db` — PostGIS (порт `5432` на всех интерфейсах VPS)
- `monitor-collector` — планировщик ETL (03:00 / 04:00 / 05:00, Europe/Moscow)
- `monitor-api` — M2M HTTP API приёма genplan photo meta (порт `8000`)

## 4. Перенос базы данных с локальной машины

Выполняется **на компьютере**, где уже есть рабочая БД с нужными данными.

### 4.1 Создать дамп

```bash
cd /path/to/MONITOR
docker compose exec -T db pg_dump -U monitor -d monitor -Fc --no-owner --no-acl -f /tmp/monitor_full.dump
docker cp monitor-db:/tmp/monitor_full.dump ./monitor_full.dump
```

### 4.2 Скопировать на VPS

```bash
scp -i <path_to_ssh_key> ./monitor_full.dump root@<server_ip>:/tmp/monitor_full.dump
```

Пример для сервера `77.222.63.161`:

```bash
scp -i id_rsa/id_rsa ./monitor_full.dump root@77.222.63.161:/tmp/monitor_full.dump
```

### 4.3 Восстановить на VPS

```bash
ssh -i <path_to_ssh_key> root@<server_ip>
cd /opt/monitor
docker cp /tmp/monitor_full.dump monitor-db:/tmp/monitor_full.dump
docker compose exec -T db pg_restore -U monitor -d monitor --clean --if-exists --no-owner --no-acl /tmp/monitor_full.dump
docker compose exec -T db psql -U monitor -d monitor < sql/08_reports_geom.sql
```

Пароль для подключения к БД после восстановления — из `.env` на VPS (`POSTGRES_PASSWORD`). Если при первом запуске контейнера пароль уже был задан, он должен совпадать с тем, что ожидает клиент.

## 5. Firewall (опционально, рекомендуется)

PostgreSQL слушает `0.0.0.0:5432`. Ограничьте доступ доверенными IP:

```bash
# пример: разрешить только свой IP
ufw allow from <your_ip> to any port 5432 proto tcp
ufw reload
```

Либо открыть для всех (менее безопасно):

```bash
ufw allow 5432/tcp
ufw reload
```

## 6. Проверка после деплоя

```bash
cd /opt/monitor
docker compose ps
docker compose logs collector --tail 100
```

Ручной запуск задач:

```bash
docker compose exec collector python -m collector.scheduler --run data_mos
docker compose exec collector python -m collector.scheduler --run lens_pipeline
docker compose exec collector python -m collector.scheduler --run genplan
docker compose exec -T db psql -U monitor -d monitor < sql/08_reports_geom.sql
```

Проверка в БД:

```bash
docker compose exec -T db psql -U monitor -d monitor -c "
SELECT schemaname, count(*) AS tables
FROM pg_tables
WHERE schemaname IN ('data_mos','lens','stroymonitoring','genplan','collector')
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

## 7. Подключение к БД из интернета

Параметры (подставьте пароль из `.env` на VPS):

| Параметр | Значение |
|----------|----------|
| Host | IP VPS (например `77.222.63.161`) |
| Port | `5432` |
| Database | `monitor` |
| User | `monitor` |
| Password | из `POSTGRES_PASSWORD` |

Строка подключения:

```
postgresql://monitor:<password>@77.222.63.161:5432/monitor
```

## 8. Обновление версии на сервере

```bash
cd /opt/monitor
git pull origin main
docker compose up -d --build
docker compose ps
docker compose exec -T db psql -U monitor -d monitor < sql/08_reports_geom.sql
docker compose exec -T db psql -U monitor -d monitor < sql/10_genplan_multi_tables.sql
docker compose exec -T db psql -U monitor -d monitor < sql/15_genplan_photo_meta_uuid.sql
```

При изменении схемы SQL может потребоваться повторный перенос дампа с локальной машины (раздел 4) или ручное применение миграций из каталога `sql/` (включая `sql/08_reports_geom.sql`, `sql/10_genplan_multi_tables.sql`, `sql/15_genplan_photo_meta_uuid.sql`).

## 9. Genplan M2M API (приём photo meta)

Коллеги отправляют JSON метаданных фотографий на MONITOR в push-режиме (`PUT /api/photos/meta/{uuid}`). Данные сохраняются в `genplan.photo_meta` с upsert по `uuid`.

Домен не используется — доступ по IP VPS, например `http://77.222.63.161:8000`. Протокол HTTP (без TLS).

Документация для коллег:

- `genplan api/ONBOARDING.md` — быстрый старт
- `genplan api/monitor-api-doc.md` — контракт API
- `genplan api/monitor_client.py` — пример Python-клиента

### 9.1 Чеклист деплоя API

- [ ] Код на VPS актуален (`git pull`)
- [ ] В `.env` задан `MONITOR_API_KEY` (без него API отвечает `503`)
- [ ] В `.env` задан `MONITOR_API_PUBLIC_BASE_URL=http://<IP_VPS>:8000`
- [ ] Применена миграция `sql/15_genplan_photo_meta_uuid.sql` (обязательно на **существующей** БД; на новой — подхватывается initdb)
- [ ] Запущен сервис `api`: `docker compose up -d --build api`
- [ ] Порт `8000` открыт в firewall **только для IP коллег**
- [ ] Проверены `health` и тестовый `PUT`

### 9.2 Запуск и миграция

```bash
cd /opt/monitor

# миграция (если БД уже была до появления API)
docker compose exec -T db psql -U monitor -d monitor < sql/15_genplan_photo_meta_uuid.sql

# поднять API (или весь стек)
docker compose up -d --build api
docker compose ps
```

### 9.3 Firewall для порта 8000

```bash
# разрешить только IP коллеги (пример)
ufw allow from <colleague_ip> to any port 8000 proto tcp
ufw reload
```

Порт `5432` по-прежнему не открывать для всего интернета.

### 9.4 Проверка после деплоя

```bash
curl -s http://77.222.63.161:8000/health
# ожидается: {"status":"ok"}

curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "http://77.222.63.161:8000/api/photos/meta/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "status": "done",
    "lat": 55.78418187985141,
    "lng": 37.74234417284182,
    "image_name": "test.jpg"
  }'
# первая отправка: HTTP 201, повторная с тем же uuid: HTTP 200

docker compose exec -T db psql -U monitor -d monitor -c "
SELECT uuid, status, lat, lng, loaded_at
FROM genplan.photo_meta
WHERE uuid = '550e8400-e29b-41d4-a716-446655440000';
"
```

### 9.5 Что передать коллегам

| Параметр | Значение |
|----------|----------|
| Base URL | `http://77.222.63.161:8000` |
| Метод | `PUT /api/photos/meta/{uuid}` |
| Auth | `Authorization: Bearer <MONITOR_API_KEY>` |
| Формат тела | JSON как в `genplan api/monitor-api-doc.md` |

Передаётся **только JSON meta**, не файл изображения.

### 9.6 Ограничения

- HTTPS не настроен (доступ по голому IP)
- `GET` для чтения meta не реализован — endpoint только **принимает** данные
- Nightly `genplan_fetch` может работать параллельно как резервный канал

## Расписание задач

| Время (MSK) | Задача | Описание |
|-------------|--------|----------|
| 03:00 | `data_mos` | 8 экспортов data.mos.ru |
| 04:00 | `lens_pipeline` | `lens_sync` + `stroymonitoring_sync` |
| 05:00 | `genplan` | импорт `jsons_genplan/*.json` в `genplan.order`, `photo_meta`, `upload`, `uuid_area` (тип по структуре JSON) |

Подробнее о сервисах и таблицах — в [README.md](README.md).
