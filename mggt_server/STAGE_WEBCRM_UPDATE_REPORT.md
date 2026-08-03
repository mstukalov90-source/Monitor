# Обновление WebCRM на `.219` — отчёт

**Дата:** 2026-07-28 (MSK)  
**Сервер:** `172.21.198.219`  
**Источник:** SWEB `77.222.63.161` (код + готовая статика)  
**Цель:** подтянуть UI/код WebCRM до версии SWEB без слепых SQL и без смены локального `.env`

---

## Диагноз (до)

| Хост | `/var/www/monitor-webcrm` | JS bundle |
|------|---------------------------|-----------|
| `.219` | mtime ~2026-06-26 | `index-DbwKKtDE.js` |
| SWEB | mtime ~2026-07-27 | `index-BDGpf9Fu.js` |

БД на `.219` уже была копией SWEB (этап 1); отставало только приложение.

---

## Что сделано

### 1. Бэкап на `.219`

| Путь | Назначение |
|------|------------|
| `/opt/monitor/webcrm.bak.20260728/` | код (без `venv` / `node_modules`) |
| `/var/www/monitor-webcrm.bak.20260728/` | статика SPA |
| `/tmp/webcrm.env.keep` | сохранённый `backend/.env` |

Сохранённые ключи `.env`: `DB_HOST=127.0.0.1`, `PHOTO_SFTP_ENABLED=false`.

### 2. Копия SWEB → Mac → `.219`

Исключено: `backend/venv`, `frontend/node_modules`, `backend/.env`.

| Шаг | Источник → назначение |
|-----|------------------------|
| код | SWEB `/opt/monitor/webcrm/` → Mac `.migration_stage1/webcrm_sweb/` → `.219:/opt/monitor/webcrm/` |
| www | SWEB `/var/www/monitor-webcrm/` → Mac `.migration_stage1/webcrm_www/` → `.219:/var/www/monitor-webcrm/` |

SWEB: только read/`rsync`; контейнеры **не** останавливали.

### 3. `.env` + deps + restart

- Восстановлен `/opt/monitor/webcrm/backend/.env` из `/tmp/webcrm.env.keep`
- `pip install -r requirements.txt` в существующий `venv`
- `systemctl restart monitor-webcrm`

### 4. SQL

**Не запускались.** Схема уже из dump SWEB; слепой прогон `sql/0*.sql` опасен (см. `docs/webcrm_tasks_deletion_investigation.md`).  
На `.219` есть таблица `webcrm.schema_migrations` (пустая по версиям на момент проверки); новый `deploy/deploy.sh` с tracking уже в дереве кода после rsync — на будущее.

---

## Проверки

| # | Проверка | Факт | Статус |
|---|----------|------|--------|
| 1 | `GET :8080/health` | `{"status":"ok"}` | **OK** |
| 2 | `systemctl is-active monitor-webcrm` | `active` | **OK** |
| 3 | SPA bundle через `:80` | `index-BDGpf9Fu.js` | **OK** (как на SWEB) |
| 4 | `DB_HOST` / `PHOTO_SFTP_ENABLED` | `127.0.0.1` / `false` | **OK** |
| 5 | `SELECT count(*) FROM crm.tasks` | **45253** (без просадки) | **OK** |
| 6 | SWEB docker | Up (api/collector/db) | **OK** |

На диске остался старый asset `index-DbwKKtDE.js` (не мешает: `index.html` ссылается на `BDGpf9Fu`).

---

## Проблемы

Критических нет. SQL-миграции сознательно пропущены; публичный HTTPS / cutover смежников — вне скоупа.

---

## Rollback

```bash
# код
rsync -a --delete /opt/monitor/webcrm.bak.20260728/ /opt/monitor/webcrm/
cp -a /tmp/webcrm.env.keep /opt/monitor/webcrm/backend/.env
# www
rsync -a --delete /var/www/monitor-webcrm.bak.20260728/ /var/www/monitor-webcrm/
systemctl restart monitor-webcrm
```

---

## Итог

WebCRM на `.219` обновлён до версии SWEB (код + статика `index-BDGpf9Fu.js`), локальный `.env` сохранён, CRM counts без изменений, SWEB тест жив.
