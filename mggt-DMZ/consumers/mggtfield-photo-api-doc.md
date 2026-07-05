# Документация MONITOR API — загрузка полевых фотографий (Android, DMZ)

API принимает **бинарные файлы** JPEG/PNG и сохраняет их на **сервере Б** в `/opt/monitor/mggtfield_photo/`. DMZ только проксирует запрос.

> Текущий прод до cutover: `http://77.222.63.161:8000` — см. [`mggtfield-photo-api-doc.md`](../../mggtfield-photo-api-doc.md)

## Подключение

| Этап | Base URL |
|------|----------|
| Внутренний тест | `http://172.21.198.222:8000` |
| Прод (внешний IP) | `http://<DMZ_PUBLIC_IP>:8000` |

| Параметр | Значение |
|----------|----------|
| Протокол | HTTP (без TLS) |
| Auth | `Authorization: Bearer <MONITOR_API_KEY>` |

## Загрузка фотографии

`POST http://172.21.198.222:8000/api/mggtfield/photos`

**Заголовки:**

```
Authorization: Bearer <MONITOR_API_KEY>
Accept: application/json
```

**Тело:** `multipart/form-data`, поле `file` (JPEG или PNG).

**Пример (curl):**

```bash
export MONITOR_BASE_URL="http://172.21.198.222:8000"
export MONITOR_API_KEY="<ключ>"

curl -s -w "\nHTTP %{http_code}\n" -X POST \
  "$MONITOR_BASE_URL/api/mggtfield/photos" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json" \
  -F "file=@/path/to/photo.jpg;type=image/jpeg;filename=field_2026-06-19_001.jpg"
```

**Ответ `201 Created`:**

```json
{
  "saved_as": "field_2026-06-19_001.jpg",
  "size_bytes": 245678,
  "content_type": "image/jpeg"
}
```

## Android (OkHttp)

```kotlin
fun uploadFieldPhoto(baseUrl: String, apiKey: String, photoFile: File): String {
    val client = OkHttpClient()
    val body = MultipartBody.Builder()
        .setType(MultipartBody.FORM)
        .addFormDataPart(
            "file",
            photoFile.name,
            photoFile.asRequestBody("image/jpeg".toMediaType()),
        )
        .build()

    val request = Request.Builder()
        .url("$baseUrl/api/mggtfield/photos")
        .header("Authorization", "Bearer $apiKey")
        .header("Accept", "application/json")
        .post(body)
        .build()

    client.newCall(request).execute().use { response ->
        if (!response.isSuccessful) {
            throw IllegalStateException("Upload failed: HTTP ${response.code}")
        }
        return response.body!!.string()
    }
}

// baseUrl = "http://172.21.198.222:8000"
```

## Ограничения

| Параметр | Значение |
|----------|----------|
| Форматы | JPEG, PNG |
| Макс. размер | 20 MiB |
| Имя файла | `[A-Za-z0-9._-]`, макс. 200 символов |

## Коды ошибок

| HTTP | Причина |
|------|---------|
| 400 | Нет файла, неверный формат |
| 401 | Неверный API-ключ |
| 413 | Файл > 20 MiB |
| 503 | Ошибка записи на backend |

## Проверка

`GET http://172.21.198.222:8000/health` — `{"status":"ok"}`

## Сценарий интеграции

1. Уникальное имя файла на клиенте
2. `POST /api/mggtfield/photos` — загрузка
3. При необходимости — `PUT /api/photos/meta/{uuid}` (см. [`monitor-api-doc.md`](monitor-api-doc.md))

При сетевой ошибке повторяйте тот же `POST` с тем же именем — идемпотентная перезапись.
