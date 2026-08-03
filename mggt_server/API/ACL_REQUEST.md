# Заявка сетевикам — публикация M2M MONITOR

> **Статус: РЕШЕНО (2026-08-03).**  
> Публичный `https://monitor-crm.mggt.ru` работает. Проверка с SWEB (`77.222.63.161`):  
> `GET /health` → **200** `{"status":"ok"}`; `PUT /api/uuids/…` → **201**, запись в `genplan.uuid_api` на `172.21.198.219`.  
> Документ ниже — архив заявки и логов на период, когда доступ был закрыт.

**Дата заявки:** 2026-07-28  
**Сервис:** MONITOR M2M API для смежников (genplan)  
**Домен:** `monitor-crm.mggt.ru`  
**Прод:** `172.21.198.219`

---

## Кратко: что просили

Открыть/настроить публикацию HTTPS `monitor-crm.mggt.ru` так, чтобы с **интернета** запросы доходили до прод-сервера MONITOR и отвечали приложением (не 403/504 края).

| Параметр | Значение |
|----------|----------|
| Домен | `monitor-crm.mggt.ru` |
| Публичный IP (DNS с интернета) | `91.246.17.237` |
| Целевой бэкенд | `172.21.198.219:80` (nginx на MONITOR) |

---

## Проблема (на момент заявки)

Смежники должны слать данные на `https://monitor-crm.mggt.ru`. С внешнего хоста домен резолвился, TLS устанавливался, но край отдавал **403 Forbidden** / позже **timeout** — до приложения MONITOR запрос не доходил.

Прямой доступ на `172.21.198.219` с интернета/VPS тоже невозможен (timeout) — ожидаемо для корпсети.

---

## Доказательства: тесты с SWEB (архив)

### Закрыто (2026-07-28 … 2026-08-03 до фикса)

```text
GET https://monitor-crm.mggt.ru/health  → 403 Forbidden / timeout
PUT https://monitor-crm.mggt.ru/api/uuids/... → 403 / timeout
```

### Открыто (2026-08-03 ~10:34 MSK, с `77.222.63.161`)

```text
$ getent hosts monitor-crm.mggt.ru
91.246.17.237   monitor-crm.mggt.ru

$ curl -sS https://monitor-crm.mggt.ru:443/health
{"status":"ok"}
http_code:200

$ curl -sS -X PUT https://monitor-crm.mggt.ru:443/api/uuids/f3a4b5c6-d7e8-9012-3456-123456789012 \
  -H "Authorization: Bearer <MONITOR_API_KEY>" -H "Accept: application/json"
{"uuid":"f3a4b5c6-d7e8-9012-3456-123456789012","result":"created"}
http_code:201
# строка есть в genplan.uuid_api на 172.21.198.219
```

---

## Критерий готовности — выполнен

- [x] `curl -sS https://monitor-crm.mggt.ru/health` → `{"status":"ok"}`
- [x] `PUT /api/uuids/...` с ключом → 201/409; данные на `.219`

## Контекст

| Роль | Значение |
|------|----------|
| Прод MONITOR | `172.21.198.219` |
| Публичный IP | `91.246.17.237` |
| Пакет API | `mggt_server/API/` |
| Статус cutover | [`CUTOVER_READY.md`](../CUTOVER_READY.md) |
