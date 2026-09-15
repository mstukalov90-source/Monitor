# MONITOR M2M API — пакет для смежников

**Прод Base URL:** `https://monitor-crm.mggt.ru`  
**Прод-сервер:** `172.21.198.219`  
**Тест (SWEB):** `http://77.222.63.161:8000` — не для прода  
**Ключ:** `MONITOR_API_KEY` (64 hex). Локально: [`credentials.local.md`](credentials.local.md) (в `.gitignore`).

**Статус (2026-08-03):** публикация **ok**. Проверка с SWEB: `GET /health` → 200; `PUT /api/uuids/…` → 201, запись в БД на `.219`.

```bash
curl -sS https://monitor-crm.mggt.ru/health
# {"status":"ok"}
```

## Файлы

| Файл | Назначение |
|------|------------|
| [ONBOARDING.md](ONBOARDING.md) | Быстрый старт для коллег |
| [monitor-api-doc.md](monitor-api-doc.md) | `PUT /api/photos/meta/{uuid}` |
| [monitor-uuid-api-doc.md](monitor-uuid-api-doc.md) | `PUT /api/uuids/{uuid}` |
| [monitor_client.py](monitor_client.py) | Минимальный Python-клиент (httpx) |
| [ACL_REQUEST.md](ACL_REQUEST.md) | Архив заявки на ACL (доступ открыт) |
| [credentials.local.md](credentials.local.md) | Реальный ключ (только локально) |

## Endpoints (прод)

| Метод | Путь | Auth |
|-------|------|------|
| `GET` | `/health` | нет |
| `PUT` | `/api/photos/meta/{uuid}` | Bearer |
| `PUT` | `/api/uuids/{uuid}` | Bearer |

`POST /api/mggtfield/photos` — для Android по VPN на `http://172.21.198.219:8000`, не через публичный домен смежников.

Маршруты OSRM (авто / вело / пеший, Москва) — Android по VPN на `http://172.21.198.219/osrm`, без API-ключа, не через `monitor-crm.mggt.ru`. Документация: [`../../osrm-android-api-doc.md`](../../osrm-android-api-doc.md).

Маршруты обследования заказа (WebCRM JWT, `field_route_service`) — Android по VPN на `http://172.21.198.219`, не OSRM напрямую. Документация для полевого приложения: [`../../docs/field-order-route-android.md`](../../docs/field-order-route-android.md) (пароль только локально / в `credentials.local.md`).
