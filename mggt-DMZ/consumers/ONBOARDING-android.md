# Инструкция для Android-разработчиков — подключение через DMZ

> **Текущий прод (до cutover):** host `77.222.63.161` — см. [`mggtfield-photo-api-doc.md`](../../mggtfield-photo-api-doc.md)  
> **Этот документ** — адреса DMZ после переключения.

Приложение использует **два канала**:
1. **PostgreSQL** — прямое подключение к БД (SQL-драйвер, порт 5432)
2. **HTTP API** — загрузка фотографий (`POST /api/mggtfield/photos`)

Оба проходят через DMZ-прокси на `172.21.198.222`.

---

## Адреса DMZ

| Этап | HTTP API | PostgreSQL host |
|------|----------|-----------------|
| Внутренний тест | `http://172.21.198.222:8000` | `172.21.198.222` |
| Прод (внешний IP) | `http://<DMZ_PUBLIC_IP>:8000` | `<DMZ_PUBLIC_IP>` |

| Параметр | Значение |
|----------|----------|
| PostgreSQL port | `5432` |
| Database | `monitor` |
| User | `monitor` |
| Password | из `.env` (`POSTGRES_PASSWORD`) — выдаёт администратор |
| API key | `MONITOR_API_KEY` — без изменений |

Строка подключения (внутренний тест):

```
postgresql://monitor:<password>@172.21.198.222:5432/monitor
```

---

## HTTP — загрузка фото

Полный контракт: [`mggtfield-photo-api-doc.md`](mggtfield-photo-api-doc.md)

```kotlin
val baseUrl = "http://172.21.198.222:8000"  // или <DMZ_PUBLIC_IP>
val apiKey = "<MONITOR_API_KEY>"
```

`POST $baseUrl/api/mggtfield/photos` — multipart, поле `file`, заголовок `Authorization: Bearer $apiKey`.

---

## PostgreSQL — прямое подключение

Host: `172.21.198.222` (или `<DMZ_PUBLIC_IP>` после cutover)  
Port: `5432`

TCP-соединение проксируется nginx stream на backend `172.21.198.219` — для клиента это прозрачно.

---

## Что менять в приложении при cutover

| Настройка | Было | Стало |
|-----------|------|-------|
| `DB_HOST` | `77.222.63.161` | `172.21.198.222` → `<DMZ_PUBLIC_IP>` |
| `API_BASE_URL` | `http://77.222.63.161:8000` | `http://172.21.198.222:8000` → `http://<DMZ_PUBLIC_IP>:8000` |
| `API_KEY` | — | без изменений |
| `DB_PASSWORD` | — | без изменений |

---

## Проверка с устройства / эмулятора

```bash
# Health
curl -s http://172.21.198.222:8000/health

# Upload test
curl -s -X POST "http://172.21.198.222:8000/api/mggtfield/photos" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -F "file=@test.jpg;type=image/jpeg;filename=test.jpg"
```

---

## Ограничения

- HTTP без TLS (как на SWEB)
- Макс. размер фото: 20 MiB
- Порт 5432 открыт для подключения (как на SWEB)

---

## Контакты

При ошибках 5xx / недоступности — администратор MONITOR.  
При cutover координируйте время переключения — см. [../CUTOVER.md](../CUTOVER.md).
