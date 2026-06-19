# Документация MONITOR API — загрузка полевых фотографий (Android)

API принимает **бинарные файлы** JPEG/PNG с мобильного приложения и сохраняет их на сервере в каталог `/opt/monitor/mggtfield_photo/`.

Для передачи **метаданных** (координаты, uuid и т.д.) используется отдельный endpoint — см. [`genplan api/monitor-api-doc.md`](genplan%20api/monitor-api-doc.md).

## Подключение

| Параметр | Значение |
|----------|----------|
| Base URL | `http://77.222.63.161:8000` |
| Протокол | HTTP (без TLS) |
| Auth | `Authorization: Bearer <MONITOR_API_KEY>` |

Ключ — 256-битный секрет (64 hex-символа), выдаётся администратором MONITOR. Не вставляйте ключ в URL и не храните в git.

Порт `8000` на сервере должен быть доступен с IP устройства или офиса разработчика (firewall на VPS).

## Загрузка фотографии

**Запрос:**

`POST http://77.222.63.161:8000/api/mggtfield/photos`

**Заголовки:**

```
Authorization: Bearer <MONITOR_API_KEY>
Accept: application/json
```

**Тело:** `multipart/form-data`

| Поле | Тип | Описание |
|------|-----|----------|
| `file` | файл | JPEG или PNG; имя файла задаёт клиент |

**Пример (curl):**

```bash
export MONITOR_BASE_URL="http://77.222.63.161:8000"
export MONITOR_API_KEY="<ключ_от_администратора>"

curl -s -w "\nHTTP %{http_code}\n" -X POST \
  "$MONITOR_BASE_URL/api/mggtfield/photos" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json" \
  -F "file=@/path/to/photo.jpg;type=image/jpeg;filename=field_2026-06-19_001.jpg"
```

**Ответ при успехе (`201 Created`):**

```json
{
  "saved_as": "field_2026-06-19_001.jpg",
  "size_bytes": 245678,
  "content_type": "image/jpeg"
}
```

- `saved_as` — имя файла на сервере (после санитизации; обычно совпадает с переданным)
- Повторная загрузка с **тем же именем** перезаписывает файл (удобно для retry)

## Android (OkHttp)

```kotlin
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File

fun uploadFieldPhoto(
    baseUrl: String,
    apiKey: String,
    photoFile: File,
    uploadFileName: String = photoFile.name,
): String {
    val client = OkHttpClient()
    val body = MultipartBody.Builder()
        .setType(MultipartBody.FORM)
        .addFormDataPart(
            "file",
            uploadFileName,
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
            throw IllegalStateException("Upload failed: HTTP ${response.code} ${response.body?.string()}")
        }
        return response.body!!.string()
    }
}
```

Для PNG замените media type на `image/png`.

## Android (Retrofit)

```kotlin
interface MonitorFieldPhotoApi {
    @Multipart
    @POST("/api/mggtfield/photos")
    suspend fun uploadPhoto(
        @Header("Authorization") authorization: String,
        @Part file: MultipartBody.Part,
    ): FieldPhotoUploadResponse
}

data class FieldPhotoUploadResponse(
    val saved_as: String,
    val size_bytes: Long,
    val content_type: String,
)

// Использование:
// val part = MultipartBody.Part.createFormData(
//     "file",
//     "field_001.jpg",
//     photoFile.asRequestBody("image/jpeg".toMediaType()),
// )
// api.uploadPhoto("Bearer $apiKey", part)
```

Настройте `OkHttpClient` с разумными таймаутами (загрузка с мобильной сети может занимать минуты).

## Ограничения

| Параметр | Значение |
|----------|----------|
| Форматы | JPEG (`.jpg`, `.jpeg`), PNG (`.png`) |
| Макс. размер | 20 MiB (20 971 520 байт) |
| Имя файла | Только `[A-Za-z0-9._-]`, без путей (`../` отбрасывается) |
| Макс. длина имени | 200 символов |

Содержимое проверяется как реальное изображение (не только по расширению).

## Коды ошибок

| HTTP | Причина | Действие |
|------|---------|----------|
| 400 | Нет файла, пустое имя, неверное расширение, не изображение | Исправить запрос |
| 401 | Нет или неверный API-ключ | Проверить `Authorization: Bearer ...` |
| 413 | Файл больше 20 MiB | Сжать фото или уменьшить разрешение |
| 503 | Каталог недоступен для записи | Связаться с администратором MONITOR |

## Проверка доступности

`GET http://77.222.63.161:8000/health` — без авторизации, ответ `{"status":"ok"}`.

## Рекомендуемый сценарий интеграции

1. Сформировать уникальное имя файла на клиенте (например `userId_timestamp.jpg`).
2. `POST /api/mggtfield/photos` — загрузить файл.
3. При необходимости — `PUT /api/photos/meta/{uuid}` с координатами и метаданными (отдельный контракт).

При ошибке сети повторяйте **тот же** `POST` с тем же именем файла — сервер перезапишет файл идемпотентно.

## Что нужно получить от администратора MONITOR

1. Base URL (`http://<IP_VPS>:8000`)
2. API-ключ (`MONITOR_API_KEY`)
3. Подтверждение, что ваш IP добавлен в firewall для порта 8000
