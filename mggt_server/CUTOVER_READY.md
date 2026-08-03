# Cutover — статус (прод = `.219`)

**Дата:** 2026-08-03 (MSK)  
**Основной сервер:** `172.21.198.219` (`LEN-MOSTRRAB-DCR-01P`)  
**Публичный M2M:** `https://monitor-crm.mggt.ru` — **работает**  
**SWEB** `77.222.63.161` — только **тест**

## Подтверждено с внешнего хоста (SWEB)

| Проверка | Результат |
|----------|-----------|
| `GET https://monitor-crm.mggt.ru/health` | **200** `{"status":"ok"}` |
| `PUT https://monitor-crm.mggt.ru/api/uuids/…` + Bearer | **201** `created` |
| Запись в БД | `genplan.uuid_api` на `.219` |

## Прод-стек

| Компонент | Статус |
|-----------|--------|
| БД (resync SWEB) | `crm.tasks` **46439**, fingerprint 1:1 ([STAGE_FINAL_RESYNC_REPORT.md](STAGE_FINAL_RESYNC_REPORT.md)) |
| Фото | ~987M + ~7.8G |
| Docker db/api/collector | Up |
| WebCRM | `index-0s08xR2m.js`, `DB_HOST=127.0.0.1` |
| nginx / firewalld | OK ([STAGE3](STAGE3_REPORT.md), [STAGE4](STAGE4_REPORT.md)) |
| Пакет смежникам | [`API/`](API/) |

## Адреса

| Потребитель | Адрес |
|-------------|--------|
| Смежники M2M | `https://monitor-crm.mggt.ru` |
| WebCRM | `http://172.21.198.219/` (корпсеть / VPN) |
| Android API / PG | `172.21.198.219:8000` / `:5432` (VPN→LAN) |
| Тест M2M | `http://77.222.63.161:8000` (SWEB) |

## Рекомендация по SWEB

Не использовать SWEB как прод-ingest: новые записи туда снова разведут БД. Оставить стенд для тестов; при необходимости снизить cron / не слать туда смежников.
