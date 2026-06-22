# Документация MONITOR M2M API — приём UUID фотографий

Пример uuid: `550e8400-e29b-41d4-a716-446655440000`

## Подключение (без домена)

**Base URL:** `http://77.222.63.161:8000`

Протокол **HTTP**. Тот же API-ключ, что и для приёма meta.

## Аутентификация

`Authorization: Bearer <MONITOR_API_KEY>`

## Передача UUID

Запрос:

`PUT http://77.222.63.161:8000/api/uuids/550e8400-e29b-41d4-a716-446655440000`

Заголовки:

```
Authorization: Bearer <MONITOR_API_KEY>
Accept: application/json
```

Тело запроса **не требуется** — uuid передаётся только в URL.

Данные сохраняются в таблицу `genplan.uuid_api`:

| Колонка | Источник |
|---------|----------|
| `uuid` | из URL (обязательно) |
| `file_name` | сервер: `api:{uuid}` |
| `loaded_at` | сервер: время приёма |

Ответ при успехе (`201 Created`):

```json
{
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "result": "created"
}
```

Повторная отправка того же uuid — `409 Conflict`:

```json
{
  "detail": "uuid already exists"
}
```

Запись **не обновляется** при дубликате.

## Коды ошибок

| Код | Причина |
|-----|---------|
| 400 | Пустой uuid в path |
| 401 | Нет или неверный API-ключ |
| 409 | uuid уже есть в `genplan.uuid_api` |
| 503 | На сервере не настроен `MONITOR_API_KEY` |

## Пример curl

```bash
export MONITOR_BASE_URL="http://77.222.63.161:8000"
export MONITOR_API_KEY="<ключ_от_администратора>"

curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "$MONITOR_BASE_URL/api/uuids/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json"
```

## Связанные endpoint'ы

| Endpoint | Назначение |
|----------|------------|
| `PUT /api/uuids/{uuid}` | только uuid (этот документ) |
| `PUT /api/photos/meta/{uuid}` | полный JSON meta — см. [`monitor-api-doc.md`](monitor-api-doc.md) |

## Проверка доступности

`GET http://77.222.63.161:8000/health` — без авторизации, ответ `{"status":"ok"}`.
