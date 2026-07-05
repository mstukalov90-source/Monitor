# Документация MONITOR M2M API — приём метаданных фотографий (DMZ)

Пример uuid: `550e8400-e29b-41d4-a716-446655440000`

## Подключение

| Этап | Base URL |
|------|----------|
| Внутренний тест | `http://172.21.198.222:8000` |
| Прод (внешний IP) | `http://<DMZ_PUBLIC_IP>:8000` |

Протокол **HTTP**. Порт `8000` на DMZ должен быть доступен с IP коллег.

> Текущий прод до cutover: `http://77.222.63.161:8000` — см. [`genplan api/monitor-api-doc.md`](../../genplan%20api/monitor-api-doc.md)

## Аутентификация

`Authorization: Bearer <MONITOR_API_KEY>`

Ключ — 256 бит (64 hex-символа). Выдаётся администратором MONITOR. Без изменений при переезде на DMZ.

## Передача метаданных

`PUT http://172.21.198.222:8000/api/photos/meta/550e8400-e29b-41d4-a716-446655440000`

Заголовки:

```
Authorization: Bearer <MONITOR_API_KEY>
Content-Type: application/json
Accept: application/json
```

Тело (JSON):

```json
{
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
}
```

Обязательные поля: `lat`, `lng` (числа, WGS84).

Ответ `201 Created`:

```json
{"uuid": "550e8400-e29b-41d4-a716-446655440000", "result": "created"}
```

Ответ `200 OK` (повторный uuid):

```json
{"uuid": "550e8400-e29b-41d4-a716-446655440000", "result": "updated"}
```

## Коды ошибок

| Код | Причина |
|-----|---------|
| 400 | Нет lat/lng, несовпадение uuid |
| 401 | Неверный API-ключ |
| 422 | Ошибка валидации |
| 503 | API-ключ не настроен на сервере |

## Проверка

`GET http://172.21.198.222:8000/health` — `{"status":"ok"}`

## Что не поддерживается

- Передача бинарного изображения — только JSON meta
- `GET` для чтения meta
