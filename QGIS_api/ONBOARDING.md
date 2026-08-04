# Инструкция для QGIS — скачивание фотографий MONITOR

Pull-API: сервис QGIS **скачивает** JPEG/PNG с MONITOR по HTTP из корпсети / VPN.
Файлы те же, что локально читает WebCRM (`downloaded_photo/`, `mggtfield_photo/`).

| Endpoint | Данные | Документация |
|----------|--------|--------------|
| `GET /api/qgis/photos/genplan/{uuid}` | genplan-фото по uuid | [`qgis-photo-api-doc.md`](qgis-photo-api-doc.md) |
| `GET /api/qgis/photos/field/{filename}` | полевые фото по имени файла | [`qgis-photo-api-doc.md`](qgis-photo-api-doc.md) |

Клиент: [`qgis_client.py`](qgis_client.py)

---

## Подключение (прод)

| Параметр | Значение |
|----------|----------|
| Base URL | `http://172.21.198.219:8000` |
| Протокол | HTTP |
| Auth | `Authorization: Bearer <ключ>` |
| Ключ | **256 бит** (64 hex-символа, AES-256), выдаёт администратор MONITOR |

Порт `8000` доступен из корпсети / VPN (прод `172.21.198.219`).

### Тестовый стенд (SWEB) — не прод

| Параметр | Значение |
|----------|----------|
| Base URL | `http://77.222.63.161:8000` |
| Протокол | HTTP |

## Что нужно получить от администратора MONITOR

1. **Base URL:** `http://172.21.198.219:8000`
2. **API-ключ** — одна строка из 64 hex-символов (256 бит)
3. Контакт для эскалации при ошибках 5xx

Храните ключ в секретах CI/CD или vault, не коммитьте в git.

## Быстрый старт (curl)

```bash
export MONITOR_BASE_URL="http://172.21.198.219:8000"
export MONITOR_API_KEY="<ключ_от_администратора>"

# проверка доступности
curl -s "$MONITOR_BASE_URL/health"

# genplan-фото по uuid
curl -sS -o photo.jpg -w "HTTP %{http_code}\n" \
  "$MONITOR_BASE_URL/api/qgis/photos/genplan/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: image/jpeg, image/png"

# полевое фото по имени файла
curl -sS -o field.jpg -w "HTTP %{http_code}\n" \
  "$MONITOR_BASE_URL/api/qgis/photos/field/test_upload.jpg" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: image/jpeg, image/png"
```

## Python

```python
from pathlib import Path
from qgis_client import QgisPhotoClient

with QgisPhotoClient(
    base_url="http://172.21.198.219:8000",
    api_key="your-256-bit-hex-key",
) as api:
    resp = api.get_genplan_photo("550e8400-e29b-41d4-a716-446655440000")
    resp.raise_for_status()
    Path("photo.jpg").write_bytes(resp.content)
```
