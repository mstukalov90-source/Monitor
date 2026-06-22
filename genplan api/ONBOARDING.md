# Инструкция для коллег — M2M API MONITOR (genplan)

Два endpoint'а с одним API-ключом:

| Endpoint | Данные | Документация |
|----------|--------|--------------|
| `PUT /api/uuids/{uuid}` | только uuid | [`monitor-uuid-api-doc.md`](monitor-uuid-api-doc.md) |
| `PUT /api/photos/meta/{uuid}` | JSON meta | [`monitor-api-doc.md`](monitor-api-doc.md) |

---

## Передача UUID (только идентификатор)

Регистрация uuid снимка в `genplan.uuid_api`. Тело запроса не нужно.

```bash
curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "$MONITOR_BASE_URL/api/uuids/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json"
```

- `201` — uuid записан
- `409` — uuid уже существует (повтор не обновляет запись)

Python: `api.put_uuid("550e8400-e29b-41d4-a716-446655440000")`

---

## Передача метаданных фотографии

MONITOR принимает JSON с метаданными анализа фотографий **в push-режиме**: вы отправляете данные сразу после готовности, без ожидания нашего nightly-запроса.

Формат JSON совпадает с ответом MSI Holes API в разделе «Получение данных по имеющейся фотографии» (см. [`genplan api doc.md`](genplan%20api%20doc.md)), но наш endpoint **принимает** данные (`PUT`), а не отдаёт (`GET`).

Передаётся **только JSON meta**. Файл изображения (JPEG/PNG) через этот API не загружается.

## Подключение без домена

| Параметр | Значение |
|----------|----------|
| Base URL | `http://77.222.63.161:8000` |
| Протокол | HTTP (TLS на IP без домена не используется) |
| API-ключ | 256-битный секрет (64 hex-символа), в заголовке `Authorization: Bearer ...` |

Коллегам нужен доступ с их IP до порта **8000** на `77.222.63.161`. Если запросы не доходят — уточните у администратора MONITOR, что ваш IP добавлен в firewall.

## Что нужно получить от администратора MONITOR

1. **Base URL:** `http://77.222.63.161:8000`
2. **API-ключ** — одна строка из 64 hex-символов (уровень 256 бит энтропии)
3. Контакт для эскалации при ошибках 5xx

Храните ключ в секретах CI/CD или vault, не коммитьте в git.

## Быстрый старт (curl)

```bash
export MONITOR_BASE_URL="http://77.222.63.161:8000"
export MONITOR_API_KEY="<ключ_от_администратора>"

# проверка доступности
curl -s "$MONITOR_BASE_URL/health"

# отправка meta
curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "$MONITOR_BASE_URL/api/photos/meta/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "status": "done",
    "start_at": "2026-06-03T15:49:08.933476+00:00",
    "date": "2026-05-1T15:52:34.939481+00:00",
    "disruption": true,
    "legal": true,
    "image_name": "DVN_b_SVAO_201_1_2026-04-16.jpg",
    "lat": 55.78418187985141,
    "lng": 37.74234417284182,
    "azimuth_deg": 118.4,
    "order_id": null
  }'
```

Ожидаемый ответ: HTTP `201` (первая запись) или `200` (обновление), тело:

```json
{"uuid": "550e8400-e29b-41d4-a716-446655440000", "result": "created"}
```

## Python

Готовый клиент: [`monitor_client.py`](monitor_client.py)

```python
from monitor_client import MonitorClient

payload = {
    "status": "done",
    "lat": 55.78418187985141,
    "lng": 37.74234417284182,
    "image_name": "DVN_b_SVAO_201_1_2026-04-16.jpg",
    "disruption": True,
    "legal": True,
}

with MonitorClient(
    base_url="http://77.222.63.161:8000",
    api_key="<ключ_от_администратора>",
) as api:
    resp = api.put_photo_meta("550e8400-e29b-41d4-a716-446655440000", payload)
    resp.raise_for_status()
    print(resp.json())
```

## Правила интеграции

| Правило | Описание |
|---------|----------|
| Идемпотентность | Повторный `PUT` с тем же uuid обновляет запись |
| uuid | Должен быть стабильным идентификатором снимка |
| lat / lng | Обязательны, числа в WGS84 |
| uuid в body | Если указан — должен совпадать с uuid в URL |
| Retry | При 5xx — экспоненциальный backoff; при 401 — проверьте ключ |
| Rate limit | Явного лимита нет; избегайте burst > 10 rps без согласования |

## Коды ошибок

| HTTP | Действие |
|------|----------|
| 400 | Исправить payload (lat/lng, uuid) |
| 401 | Проверить ключ и заголовок `Authorization: Bearer ...` |
| 422 | Невалидные типы полей |
| 503 | Связаться с администратором MONITOR |

Полный контракт meta: [`monitor-api-doc.md`](monitor-api-doc.md)  
Полный контракт uuid: [`monitor-uuid-api-doc.md`](monitor-uuid-api-doc.md)

## Отличие от MSI Holes API

| | MSI Holes (внешний) | MONITOR (наш приём) |
|--|---------------------|---------------------|
| Направление | MONITOR **забирает** данные | Вы **отправляете** данные |
| Метод | `GET /api/photos/meta/{uuid}` | `PUT /api/photos/meta/{uuid}` |
| Auth | OAuth2 client_credentials (Hydra) | Статический Bearer API-ключ (256 бит) |
| Адрес | `https://m2m.msi-holes.cxm.dev` | `http://77.222.63.161:8000` |
| Изображение | Отдельный `GET .../images/{uuid}` | Не поддерживается |
