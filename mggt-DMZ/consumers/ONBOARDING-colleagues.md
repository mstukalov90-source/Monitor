# Инструкция для коллег — M2M API MONITOR (genplan) через DMZ

> **Текущий прод (до cutover):** `http://77.222.63.161:8000` — см. [`genplan api/ONBOARDING.md`](../../genplan%20api/ONBOARDING.md)  
> **Этот документ** — для подключения через DMZ после переключения.

Два endpoint'а с одним API-ключом:

| Endpoint | Данные | Документация |
|----------|--------|--------------|
| `PUT /api/uuids/{uuid}` | только uuid | [`monitor-uuid-api-doc.md`](monitor-uuid-api-doc.md) |
| `PUT /api/photos/meta/{uuid}` | JSON meta | [`monitor-api-doc.md`](monitor-api-doc.md) |

---

## Адреса DMZ

| Этап | Base URL |
|------|----------|
| Внутренний тест (VPN / корп. сеть) | `http://172.21.198.222:8000` |
| Прод после выдачи внешнего IP | `http://<DMZ_PUBLIC_IP>:8000` |

Протокол: **HTTP** (без TLS). API-ключ — без изменений.

---

## Передача UUID

```bash
export MONITOR_BASE_URL="http://172.21.198.222:8000"
export MONITOR_API_KEY="<ключ_от_администратора>"

curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "$MONITOR_BASE_URL/api/uuids/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json"
```

- `201` — uuid записан
- `409` — uuid уже существует

---

## Передача метаданных фотографии

MONITOR принимает JSON **в push-режиме**. Передаётся **только JSON meta**, не файл изображения.

```bash
curl -s "$MONITOR_BASE_URL/health"

curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "$MONITOR_BASE_URL/api/photos/meta/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "status": "done",
    "lat": 55.78418187985141,
    "lng": 37.74234417284182,
    "image_name": "DVN_b_SVAO_201_1_2026-04-16.jpg",
    "disruption": true,
    "legal": true
  }'
```

Ожидаемый ответ: HTTP `201` (создание) или `200` (обновление).

---

## Что нужно от администратора MONITOR

1. **Base URL** — адрес DMZ (см. таблицу выше)
2. **API-ключ** — 64 hex-символа, заголовок `Authorization: Bearer ...`
3. Подтверждение, что ваш IP добавлен в firewall DMZ для порта **8000**

---

## Python

Клиент из основного репозитория: [`genplan api/monitor_client.py`](../../genplan%20api/monitor_client.py)

```python
from monitor_client import MonitorClient

with MonitorClient(
    base_url="http://172.21.198.222:8000",  # или <DMZ_PUBLIC_IP>
    api_key="<ключ>",
) as api:
    resp = api.put_photo_meta("550e8400-e29b-41d4-a716-446655440000", {
        "status": "done",
        "lat": 55.78418187985141,
        "lng": 37.74234417284182,
        "image_name": "test.jpg",
    })
    resp.raise_for_status()
```

---

## Правила интеграции

| Правило | Описание |
|---------|----------|
| Идемпотентность | Повторный `PUT` с тем же uuid обновляет запись (meta) |
| uuid only | `PUT /api/uuids/{uuid}` — insert-only, дубликат → 409 |
| lat / lng | Обязательны для meta, WGS84 |
| Retry | При 5xx — backoff; при 401 — проверьте ключ |

Полные контракты: [`monitor-api-doc.md`](monitor-api-doc.md), [`monitor-uuid-api-doc.md`](monitor-uuid-api-doc.md)

---

## Отличие от MSI Holes API

| | MSI Holes | MONITOR (наш приём) |
|--|-----------|---------------------|
| Направление | MONITOR забирает | Вы отправляете |
| Метод | `GET /api/photos/meta/{uuid}` | `PUT /api/photos/meta/{uuid}` |
| Auth | OAuth2 | Bearer API-ключ |
| Адрес | `https://m2m.msi-holes.cxm.dev` | DMZ Base URL (см. выше) |
