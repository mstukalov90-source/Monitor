# Этап 3 — отчёт: nginx WebCRM / M2M

**Дата:** 2026-07-28 (MSK)  
**Сервер:** `172.21.198.219` (`LEN-MOSTRRAB-DCR-01P`)  
**План:** развести M2M (`:8000`) и WebCRM (`:8080`) на nginx `:80`

---

## Что изменено

| Элемент | Значение |
|---------|----------|
| Конфиг в репо | [`nginx/monitor-webcrm.conf`](nginx/monitor-webcrm.conf) |
| На сервере | `/etc/nginx/conf.d/monitor-webcrm.conf` |
| Бэкап до изменений | `/etc/nginx/conf.d/monitor-webcrm.conf.bak.stage3` |
| `nginx -t` | OK |
| `systemctl reload nginx` | OK, `active` |

### Маршрутизация

| Location | Upstream |
|----------|----------|
| `= /health` | `127.0.0.1:8000` (M2M) |
| `/api/photos/meta/` | `:8000` |
| `/api/uuids/` | `:8000` |
| `/api/mggtfield/` | `:8000` (body 20m, `proxy_request_buffering off`) |
| `/api/` (остальное) | `127.0.0.1:8080` (WebCRM) |
| `/` | SPA `/var/www/monitor-webcrm` |

`server_name`: `172.21.198.219 monitor-crm.mggt.ru`

SWEB **не изменялся**.

---

## Результаты проверок

| # | Команда / проверка | Факт | Статус |
|---|-------------------|------|--------|
| 1 | `GET http://127.0.0.1/health` | `200` `{"status":"ok"}`, `Server: nginx` | **OK** |
| 2 | `GET http://127.0.0.1:8000/health` | `200` `{"status":"ok"}`, `server: uvicorn` | **OK** |
| 3 | `GET http://127.0.0.1:8080/health` | `200` `{"status":"ok"}` (WebCRM напрямую) | **OK** |
| 4 | `GET http://127.0.0.1/` | `200` HTML SPA (`<!doctype html>`) | **OK** |
| 5 | `PUT http://127.0.0.1/api/uuids/{uuid}` без Bearer | `401` `Missing or invalid Authorization header`, `www-authenticate: Bearer` | **OK** (M2M через nginx) |
| 6 | `PUT http://127.0.0.1:8000/api/uuids/{uuid}` без Bearer | тот же `401` M2M | **OK** |
| 7 | `POST http://127.0.0.1/api/auth/login` (WebCRM) | `401` `{"detail":"Неверный логин или пароль"}` — ответ WebCRM, не M2M | **OK** (разведение `/api/`) |
| 8 | `PUT http://127.0.0.1/api/photos/meta/{uuid}` без Bearer | `401` Bearer M2M | **OK** |

Доказательство split: один и тот же префикс `/api/` даёт **Bearer M2M** на `/api/uuids/` и **русскоязычный WebCRM auth** на `/api/auth/login`.

---

## Проблемы

### Критические

**Критических проблем нет.**

### Замечания (не блокеры этапа 3)

| ID | Симптом | Причина | Статус / workaround |
|----|---------|---------|---------------------|
| Z1 | `GET /health` через nginx больше не отражает health WebCRM | По плану `location = /health` → M2M | **Ожидаемо.** WebCRM: `http://127.0.0.1:8080/health` или мониторинг через systemd/uvicorn |
| Z2 | Тела `/health` у M2M и WebCRM одинаковые (`{"status":"ok"}`) | Оба сервиса так отвечают | Маршрут подтверждён через `401`+`www-authenticate` на M2M paths, не через body health |
| Z3 | `https://monitor-crm.mggt.ru` с интернета → **403** | ACL/WAF на крае (этап 0); трафик до `.219` не доходит | **Вне скоупа этапа 3.** Повторить проверки снаружи после открытия ACL (этап 4+) |
| Z4 | Backend-порт публикации шлюза (`:80` vs `:8000`) формально не подтверждён с интернета | Этап 0 | Этап 3 готовит приём на **`:80`**; если шлюз бьёт в `:8000`, nginx-split для смежников не обязателен, прямой M2M уже слушает `:8000` |

---

## Откат

```bash
ssh root@172.21.198.219
cp -a /etc/nginx/conf.d/monitor-webcrm.conf.bak.stage3 /etc/nginx/conf.d/monitor-webcrm.conf
nginx -t && systemctl reload nginx
```

---

## Следующие шаги

- Этап 4: firewalld / ACL шлюза  
- Повторная проверка `https://monitor-crm.mggt.ru/health` после открытия публикации  
- Cutover смежников на домен
