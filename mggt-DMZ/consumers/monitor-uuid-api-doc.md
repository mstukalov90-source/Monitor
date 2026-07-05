# Документация MONITOR M2M API — приём UUID (DMZ)

Пример uuid: `550e8400-e29b-41d4-a716-446655440000`

## Подключение

| Этап | Base URL |
|------|----------|
| Внутренний тест | `http://172.21.198.222:8000` |
| Прод (внешний IP) | `http://<DMZ_PUBLIC_IP>:8000` |

> Текущий прод до cutover: `http://77.222.63.161:8000` — см. [`genplan api/monitor-uuid-api-doc.md`](../../genplan%20api/monitor-uuid-api-doc.md)

## Аутентификация

`Authorization: Bearer <MONITOR_API_KEY>`

## Передача UUID

`PUT http://172.21.198.222:8000/api/uuids/550e8400-e29b-41d4-a716-446655440000`

Тело запроса **не требуется**.

Ответ `201 Created`:

```json
{"uuid": "550e8400-e29b-41d4-a716-446655440000", "result": "created"}
```

Повтор → `409 Conflict`:

```json
{"detail": "uuid already exists"}
```

## Пример curl

```bash
export MONITOR_BASE_URL="http://172.21.198.222:8000"
export MONITOR_API_KEY="<ключ>"

curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "$MONITOR_BASE_URL/api/uuids/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json"
```

## Связанные endpoint'ы

| Endpoint | Назначение |
|----------|------------|
| `PUT /api/uuids/{uuid}` | только uuid (этот документ) |
| `PUT /api/photos/meta/{uuid}` | полный JSON meta — [`monitor-api-doc.md`](monitor-api-doc.md) |

## Проверка

`GET http://172.21.198.222:8000/health` — `{"status":"ok"}`
