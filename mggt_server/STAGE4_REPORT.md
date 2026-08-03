# Этап 4 — отчёт: firewalld + ограничение внешнего доступа (только M2M)

**Дата:** 2026-07-28 (MSK)  
**Сервер:** `172.21.198.219`  
**Цель:** снаружи только M2M; WebCRM и PostgreSQL — из корпсети

---

## Что изменено

| Элемент | Путь |
|---------|------|
| Скрипт firewalld | [`firewall/server-firewalld.sh`](firewall/server-firewalld.sh) |
| nginx (geo) | [`nginx/monitor-webcrm.conf`](nginx/monitor-webcrm.conf) |
| Бэкап nginx | `/etc/nginx/conf.d/monitor-webcrm.conf.bak.stage4` |

### firewalld (итог)

| Source | Ports | Назначение |
|--------|-------|------------|
| `127.0.0.1` | `5432` | WebCRM → PG на localhost |
| `172.21.0.0/16` | `80`, `8000`, `5432` | корпсеть (в т.ч. `.198`, VPN `.248`) |
| `192.168.1.217` | `80`, `8000` | внутр. шлюз домена — **только M2M** (без PG) |
| ~~`172.21.198.222`~~ | — | **удалено** (legacy DMZ) |

Services зоны: `ssh`, `mdns`, `dhcpv6-client` (без изменений).  
PG **не** открыт шлюзу и миру.

### nginx geo

```nginx
geo $is_internal {
    default 0;
    127.0.0.0/8 1;
    172.21.0.0/16 1;
}
```

- M2M paths (`/health`, `/api/photos/meta/`, `/api/uuids/`, `/api/mggtfield/`) — без ограничения по geo  
- `/api/` (WebCRM) и `/` (SPA) — `403`, если `$is_internal = 0`

---

## Проверки

| # | Проверка | Факт | Статус |
|---|----------|------|--------|
| 1 | `GET 127.0.0.1/health` | `200` M2M ok | **OK** |
| 2 | `GET 127.0.0.1:8000/health` | `200` | **OK** |
| 3 | `GET 127.0.0.1/` SPA | `200` HTML | **OK** |
| 4 | `POST /api/auth/login` с localhost | `401` WebCRM (рус.) | **OK** |
| 5 | `PUT /api/uuids/…` без ключа | `401` Bearer M2M | **OK** |
| 6 | `GET http://172.21.198.219/` с Mac (маршрут via `172.21.248.1`) | `200` SPA после расширения до `/16` | **OK** |
| 7 | `GET http://172.21.198.219/health` с Mac | `{"status":"ok"}` | **OK** |
| 8 | Rich rules без `.222` | отсутствуют | **OK** |
| 9 | `https://monitor-crm.mggt.ru/health` с SWEB | **403** Forbidden (Request ID) — край | **PENDING** ACL |
| 10 | SWEB docker | Up (не трогали) | **OK** |

---

## Проблемы

### Критические (исправлены в ходе этапа)

| ID | Симптом | Причина | Решение |
|----|---------|---------|---------|
| P1 | После первой версии правил Mac потерял `:80` (`connection refused` / timeout) | Rich rules только на `172.21.198.0/24`, а Mac → `.219` идёт через шлюз **`172.21.248.1`** (другая подсеть `172.21`) | Расширен allowlist и nginx geo до **`172.21.0.0/16`**. Повторная проверка Mac: SPA `200`, health ok |

### Замечания

| ID | Симптом | Статус |
|----|---------|--------|
| Z1 | Публичный HTTPS `91.246.17.237` → **403** | Вне скоупа `.219`; firewall/nginx готовы принимать шлюз `192.168.1.217`. Нужен ACL на крае |
| Z2 | Source IP после SNAT с края может отличаться от `192.168.1.217` | При появлении трафика — tcpdump и доп. rich-rule; зафиксировать здесь |
| Z3 | `172.21.0.0/16` шире исходного плана `/24` | Сознательно: иначе админы/VPN вне `.198` без WebCRM. Интернет в `/16` не входит |

### Критических открытых проблем нет

(публичный 403 — блокер cutover смежников, не блокер этапа 4 на сервере)

---

## Откат

```bash
# nginx
cp -a /etc/nginx/conf.d/monitor-webcrm.conf.bak.stage4 /etc/nginx/conf.d/monitor-webcrm.conf
# или .bak.stage3
nginx -t && systemctl reload nginx

# firewalld — вручную убрать/вернуть rich rules; снимок «до» в этом отчёте § firewalld BEFORE в логе применения
```

---

## Следующее

- Открытие ACL на `monitor-crm.mggt.ru` / `91.246.17.237`  
- Повтор `curl https://monitor-crm.mggt.ru/health` с SWEB  
- Этап 5 уже сделан (`MONITOR_API_PUBLIC_BASE_URL`)  
- Этапы 6–7: проверки и cutover смежников
