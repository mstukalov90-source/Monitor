# Финальный resync SWEB → `.219` — отчёт

**Дата:** 2026-08-03 (MSK)  
**Источник:** SWEB `77.222.63.161`  
**Цель:** `172.21.198.219`  
**Режим:** вариант 3 — контейнеры SWEB **не** останавливали

---

## Preflight (до)

| Объект | SWEB | `.219` |
|--------|-----:|-------:|
| `crm.tasks` | 46439 | 45432 |
| `crm.tasks_field` | 34594 | 33678 |
| `mggtfield_photo` | ~7.8G | ~6.6G |
| WebCRM JS | `index-0s08xR2m.js` | `index-BDGpf9Fu.js` |

Бэкап на `.219`: `webcrm.bak.20260803`, `monitor-webcrm.bak.20260803`, `/tmp/webcrm.env.keep`.

---

## Что сделано

1. **Dump:** `pg_dump -Fc -Z6` → Mac `.migration_stage1/monitor_sweb_20260803.dump` (~295M)
2. **Wipe + restore на `.219`:**
   - `docker compose down` + `docker volume rm monitor_pgdata`
   - Первый restore через stdin — fail (magic header)
   - Restore через `docker cp` — конфликт со stub-таблицами из `docker-entrypoint-initdb.d`
   - **Рабочий путь:** `DROP DATABASE` / `CREATE DATABASE` + PostGIS extensions → `pg_restore` из файла в контейнере
   - Ошибки только **`pg_cron`** / уже существующие postgis schemas (`tiger`/`topology`) — 9 шт., на данные не влияют
3. **Фото:** rsync `downloaded_photo` + `mggtfield_photo` SWEB→Mac→`.219`
4. **WebCRM:** rsync код + `/var/www/monitor-webcrm`; `.env` возвращён (`DB_HOST=127.0.0.1`); `systemctl restart monitor-webcrm`

---

## Верификация (после)

| Метрика | SWEB | `.219` |
|---------|------|--------|
| `crm.tasks` | 46439 | 46439 |
| keys/rows MD5 | `aabad695…` / `aec5f99c…` | **совпали** |
| `crm.tasks_field` | 34594 | 34594 |
| `crm.tasks_area` | 601 | 601 |
| `crm.tasks_clear` | 4290 | 4290 |
| `crm.users` | 13 | 13 |
| `genplan.uuid_api` | 7381 | 7381 |
| `genplan.photo_meta` | 220107 | 220107 |
| WebCRM bundle | `index-0s08xR2m.js` | `index-0s08xR2m.js` |
| `downloaded_photo` | 987M | 987M |
| `mggtfield_photo` | 7.8G | 7.9G (du locale) |
| `:8000` / `:8080` health | — | ok / ok |
| SWEB docker | Up | — (не трогали) |

---

## Замечания

- Публичный `https://monitor-crm.mggt.ru` по-прежнему вне скоупа (ACL).
- SWEB оставлен как тест; для прода смежники должны писать только на `https://monitor-crm.mggt.ru` (иначе БД снова разъедется).
