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
```

При изменении схемы SQL может потребоваться повторный перенос дампа с локальной машины (раздел 4) или ручное применение миграций из каталога `sql/` (включая `sql/08_reports_geom.sql`, `sql/10_genplan_multi_tables.sql`).

## Расписание задач

| Время (MSK) | Задача | Описание |
|-------------|--------|----------|
| 03:00 | `data_mos` | 8 экспортов data.mos.ru |
| 04:00 | `lens_pipeline` | `lens_sync` + `stroymonitoring_sync` |
| 05:00 | `genplan` | импорт `jsons_genplan/*.json` в `genplan.order`, `photo_meta`, `upload`, `uuid_area` (тип по структуре JSON) |

Подробнее о сервисах и таблицах — в [README.md](README.md).
