# Тестирование DMZ

Все проверки API и PostgreSQL выполняются **через сервер А** (`172.21.198.222`), не напрямую на `.219`.

Перед тестами убедитесь, что SWEB не затронут:

```bash
curl -s http://77.222.63.161:8000/health
# ожидается: {"status":"ok"}
```

---

## 1. Health check

```bash
curl -s http://172.21.198.222:8000/health
```

Ожидается: `{"status":"ok"}`

---

## 2. Photo meta (genplan)

```bash
export MONITOR_BASE_URL="http://172.21.198.222:8000"
export MONITOR_API_KEY="<ключ_из_.env_на_сервере_Б>"

curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "$MONITOR_BASE_URL/api/photos/meta/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "status": "done",
    "lat": 55.78418187985141,
    "lng": 37.74234417284182,
    "image_name": "dmz_test.jpg"
  }'
```

Ожидается: HTTP `201` (первая отправка) или `200` (повтор).

Проверка в БД на сервере Б:

```bash
ssh root@172.21.198.219 'cd /opt/monitor && docker compose exec -T db psql -U monitor -d monitor -c "
SELECT uuid, status, lat, lng, loaded_at
FROM genplan.photo_meta
WHERE uuid = '\''550e8400-e29b-41d4-a716-446655440000'\'';"'
```

---

## 3. UUID ingest

```bash
curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "$MONITOR_BASE_URL/api/uuids/8d4c7a74-6c6f-4e53-a93d-9a6a7d5f2f21" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json"
```

Ожидается: HTTP `201` (первая) или `409` (дубликат).

---

## 4. Загрузка полевого фото (Android)

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST \
  "$MONITOR_BASE_URL/api/mggtfield/photos" \
  -H "Authorization: Bearer $MONITOR_API_KEY" \
  -H "Accept: application/json" \
  -F "file=@/path/to/test.jpg;type=image/jpeg;filename=dmz_test_upload.jpg"
```

Ожидается: HTTP `201`, JSON с `saved_as`, `size_bytes`, `content_type`.

Файл должен появиться **на сервере Б**, не на DMZ:

```bash
ssh root@172.21.198.219 'ls -la /opt/monitor/mggtfield_photo/ | tail -5'
```

На сервере А файлов быть не должно (кроме системных логов nginx):

```bash
ssh root@172.21.198.222 'ls -la /opt/monitor 2>/dev/null || echo "каталога нет — OK"'
```

---

## 5. PostgreSQL через DMZ

```bash
psql "postgresql://monitor:<POSTGRES_PASSWORD>@172.21.198.222:5432/monitor" -c "SELECT 1 AS dmz_ok;"
```

Или с сервера А:

```bash
ssh root@172.21.198.222 'timeout 2 bash -c "echo >/dev/tcp/127.0.0.1/5432" && echo PG_proxy_OK'
```

---

## 6. Auth errors (негативные тесты)

```bash
# Без ключа — 401
curl -s -w "\nHTTP %{http_code}\n" -X PUT \
  "$MONITOR_BASE_URL/api/photos/meta/550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{"lat":55.78,"lng":37.74}'
```

---

## 7. SWEB не затронут (финальная проверка)

```bash
curl -s http://77.222.63.161:8000/health
ssh -i id_rsa/id_rsa root@77.222.63.161 'cd /opt/monitor && docker compose ps'
```

Все контейнеры SWEB должны быть `Up`.

---

## Матрица связности (быстрая)

```bash
# С Mac (VPN)
curl -s http://172.21.198.222:8000/health    # DMZ → OK
curl -s http://172.21.198.219:8000/health    # Backend напрямую → OK (до ужесточения firewall)
curl -s http://77.222.63.161:8000/health     # SWEB прод → OK
```
