# Документация MONITOR API — скачивание фотографий для QGIS

Пример uuid: `550e8400-e29b-41d4-a716-446655440000`

## Подключение

**Прод Base URL:** `http://172.21.198.219:8000`  
**Тест (SWEB):** `http://77.222.63.161:8000`

Прод — **HTTP** по IP из корпсети / VPN. API-ключ — единственный секрет в заголовке.

## Аутентификация

`Authorization: Bearer <MONITOR_API_KEY>`

Ключ — **256 бит** криптостойкой случайности (64 символа hex, AES-256).
Выдаётся администратором MONITOR. Не вставляйте ключ в URL и не коммитьте в git.

## Genplan-фото по uuid

Файлы из каталога `downloaded_photo/` (те же, что видит WebCRM на сервере).

Запрос:

`GET http://172.21.198.219:8000/api/qgis/photos/genplan/550e8400-e29b-41d4-a716-446655440000`

Заголовки:

```
Authorization: Bearer <MONITOR_API_KEY>
Accept: image/jpeg, image/png
```

Резолв файла:

1. По `uuid` читается `image_name` из `genplan.photo_meta`
2. Ищется файл с этим именем в `downloaded_photo/`
3. Если meta нет или файла нет — fallback: `{uuid}.jpg` / `{uuid}.jpeg` / `{uuid}.png`

Ответ `200 OK`: тело — бинарник JPEG или PNG (`Content-Type: image/jpeg` или `image/png`).

```bash
curl -sS -o photo.jpg -w "HTTP %{http_code}\n" \
  "http://172.21.198.219:8000/api/qgis/photos/genplan/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: image/jpeg, image/png"
```

## Полевые фото по имени файла

Файлы из каталога `mggtfield_photo/` (загрузки Android).

Запрос:

`GET http://172.21.198.219:8000/api/qgis/photos/field/test_upload.jpg`

Заголовки:

```
Authorization: Bearer <MONITOR_API_KEY>
Accept: image/jpeg, image/png
```

Имя файла — только basename с расширением `.jpg` / `.jpeg` / `.png`.
Path traversal (`../`) отклоняется.

```bash
curl -sS -o field.jpg -w "HTTP %{http_code}\n" \
  "http://172.21.198.219:8000/api/qgis/photos/field/test_upload.jpg" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: image/jpeg, image/png"
```

## Коды ошибок

| Код | Причина |
|-----|---------|
| 400 | Пустой uuid / невалидное имя файла / неверное расширение |
| 401 | Нет или неверный API-ключ |
| 404 | Файл не найден на диске (и для genplan — нет подходящего fallback) |
| 503 | На сервере не настроен `MONITOR_API_KEY` |

## Ограничения

- Только **скачивание** (GET). Загрузка фото — отдельно (`POST /api/mggtfield/photos`)
- Нет list/search: нужен известный `uuid` или имя файла
- Допустимые форматы: JPEG, PNG
- WebCRM по-прежнему читает каталоги локально; этот API — для доступа из корпсети

## Проверка доступности

`GET http://172.21.198.219:8000/health` — без авторизации, ответ `{"status":"ok"}`.

## Что нужно получить от администратора MONITOR

1. Base URL: `http://172.21.198.219:8000`
2. API-ключ (64 hex / 256 бит)
3. Контакт при 5xx
