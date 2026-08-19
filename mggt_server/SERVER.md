# MONITOR — конфигурация сервера `172.21.198.219`

Снимок конфигурации **основного прод-сервера** на **2026-08-03**.  
План переезда: [MIGRATION.md](MIGRATION.md). Статус: [../acses_status.md](../acses_status.md). Cutover: [CUTOVER_READY.md](CUTOVER_READY.md).

---

## Идентификация

| Параметр | Значение |
|----------|----------|
| Роль | Единственный **прод** (без DMZ-прослойки) |
| IP | `172.21.198.219/24` |
| Интерфейс | `ens192` |
| Шлюз сети | `172.21.198.1` |
| Hostname | `LEN-MOSTRRAB-DCR-01P` |
| ОС | RED OS 8.0.2 (`redos`, kernel `6.12.92-1.red80.x86_64`) |
| Путь проекта | `/opt/monitor` |
| SSH | `ssh root@172.21.198.219` |

---

## Железо и ресурсы

| Ресурс | Значение |
|--------|----------|
| CPU | 4 vCPU · AMD EPYC 7763 |
| RAM | 15 GiB |
| Swap | ~9.6 GiB |
| Диск `/` | LVM `ro-root` · 489 GB |

```bash
nproc
free -h
df -h /
```

---

## Публикация снаружи

| Параметр | Значение |
|----------|----------|
| Домен | `monitor-crm.mggt.ru` |
| DNS с интернета | **`91.246.17.237`** |
| DNS из корпсети | **`192.168.1.217`** |
| Публичный порт | `443` (TLS на краевом шлюзе) |
| Backend на `.219` | **`:80`** (nginx → M2M `:8000`) |
| Статус (2026-08-03) | с SWEB: `/health` **200**, `PUT /api/uuids` **201** → БД `.219` |
| Назначение снаружи | **только** M2M API смежников |
| На `.219` | TLS/`443` нет; HTTP `:80` |

**Android:** VPN-приложение → LAN, доступ к `:80` / `:8000` / `:5432`.  
WebCRM в интернет **не** публикуется — только корпсеть / VPN.

---

## Слушающие порты (факт 2026-08-03)

| Порт | Процесс | Назначение |
|------|---------|------------|
| `22` | `sshd` | SSH |
| `80` | `nginx` | SPA + proxy M2M → `:8000`, WebCRM `/api/` → `:8080` |
| `8080` | `uvicorn` | WebCRM API, **только** `127.0.0.1` |
| `5432` | `monitor-db` | Docker PostGIS (корпсеть) |
| `8000` | `monitor-api` | Docker M2M |
| `443` | — | нет (TLS на шлюзе) |

БД: финальный resync с SWEB 2026-08-03 (`crm.tasks` **46439**). См. [STAGE_FINAL_RESYNC_REPORT.md](STAGE_FINAL_RESYNC_REPORT.md).
---

## Systemd-сервисы

| Unit | Состояние | Описание |
|------|-----------|----------|
| `nginx.service` | active | HTTP reverse proxy + статика |
| `monitor-webcrm.service` | active | FastAPI WebCRM (`uvicorn app.main:app`) |
| `docker.service` | active | контейнеры MONITOR |
| `firewalld.service` | active | фильтр пакетов |

### `monitor-webcrm.service` (кратко)

- WorkingDirectory: `/opt/monitor/webcrm/backend`
- EnvironmentFile: `/opt/monitor/webcrm/backend/.env`
- ExecStart: `.../venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080`
- Restart: `on-failure`

```bash
systemctl status nginx monitor-webcrm docker firewalld
```

---

## Nginx

| Параметр | Значение |
|----------|----------|
| Версия | nginx/1.30.2 |
| Конфиг | `/etc/nginx/conf.d/monitor-webcrm.conf` (репо: [`nginx/monitor-webcrm.conf`](nginx/monitor-webcrm.conf)) |
| Бэкап этапа 3 | `/etc/nginx/conf.d/monitor-webcrm.conf.bak.stage3` |
| `server_name` | `172.21.198.219 monitor-crm.mggt.ru` |
| root | `/var/www/monitor-webcrm` |
| `= /health`, `/api/photos/meta/`, `/api/uuids/`, `/api/mggtfield/`, `/api/qgis/` | `proxy_pass http://127.0.0.1:8000` (M2M, без geo) |
| `/api/` (остальное), `/` (SPA) | WebCRM / SPA; **только** `$is_internal` (`127.0.0.0/8`, `172.21.0.0/16`), иначе `403` |

Отчёты: [STAGE3_REPORT.md](STAGE3_REPORT.md), [STAGE4_REPORT.md](STAGE4_REPORT.md).

---

## Docker Compose (`/opt/monitor`)

| Контейнер | Image / роль | Порт | Статус после этапа 1–3 |
|-----------|--------------|------|-------------------------|
| `monitor-db` | `postgis/postgis:16-3.4` | `5432` | **Up** (healthy) |
| `monitor-api` | `monitor-api` (uvicorn M2M) | `8000` | **Up** |
| `monitor-collector` | `monitor-collector` (APScheduler) | — | **Up** |

| Том | Назначение |
|-----|------------|
| `monitor_pgdata` | данные PostgreSQL/PostGIS — **сохранён** |
| `/mnt/monitor/ogh-zakazy` → collector | CIFS Заказы **ro** (`bind-propagation: rslave`) |

```bash
cd /opt/monitor && docker compose ps -a
docker volume ls | grep monitor
```

Файл окружения стека: `/opt/monitor/.env`  
Важные переменные (без секретов): `POSTGRES_*`, `REMOTE_DB_HOST=172.16.206.170`, `WEB_GEO_DB_HOST=172.21.198.149`, `MONITOR_API_PUBLIC_BASE_URL`, `MONITOR_API_PORT=8000`.

На 28.07 после этапа 1: `MONITOR_API_PUBLIC_BASE_URL=https://monitor-crm.mggt.ru`. WebCRM: `DB_HOST=127.0.0.1`, `PHOTO_SFTP_ENABLED=false`.

---

## WebCRM

| Параметр | Значение |
|----------|----------|
| Код | `/opt/monitor/webcrm/` |
| Frontend (prod) | `/var/www/monitor-webcrm/` |
| Backend | `127.0.0.1:8080` |
| `.env` backend | `/opt/monitor/webcrm/backend/.env` |

На 28.07 backend всё ещё смотрит на SWEB:

- `DB_HOST=77.222.63.161`
- `PHOTO_SFTP_ENABLED=true`, `PHOTO_SFTP_HOST=77.222.63.161`

Целевое состояние после переезда: `DB_HOST=127.0.0.1`, локальные каталоги фото, без SFTP на SWEB.

---

## Firewalld (факт после этапа 4)

Зона `public`, интерфейс `ens192`. Скрипт: [`firewall/server-firewalld.sh`](firewall/server-firewalld.sh).

**Services:** `ssh`, `dhcpv6-client`, `mdns`  
**Ports (глобально):** нет  
**Rich rules:**

```
source 127.0.0.1       tcp/5432 accept
source 172.21.0.0/16   tcp/80,8000,5432 accept   # корпсеть + VPN (.248 и др.)
source 192.168.1.217   tcp/80,8000 accept        # шлюз домена — M2M only
```

Legacy `.222` удалены. **PostgreSQL шлюзу и интернету не открыт.**  
Отчёт: [STAGE4_REPORT.md](STAGE4_REPORT.md).

```bash
firewall-cmd --list-all
firewall-cmd --list-rich-rules
```

---

## Связанные узлы

| Узел | IP | Роль относительно `.219` |
|------|-----|--------------------------|
| Шлюз MGGT | `192.168.1.217` | HTTPS-фронт `monitor-crm.mggt.ru` |
| SWEB | `77.222.63.161` | **тестовый** стенд |
| MONITOR Внешний | `172.21.198.222` | ex-DMZ, не в прод-схеме |
| SPS | `172.16.206.170:5432` | источник `lens_sync` |
| web_geo | `172.21.198.149:5432` | источник `stroymonitoring_sync` |

---

## Каталоги данных

| Путь | Назначение |
|------|------------|
| `/opt/monitor/downloaded_photo/` | фото genplan |
| `/opt/monitor/mggtfield_photo/` | полевые фото Android |
| `/opt/monitor/jsons_genplan/` | вход JSON для `genplan` |
| `/opt/monitor/photo_to_upload/` | очередь upload в MSI |
| `/mnt/monitor/situation` | CIFS **read-only**: `\\len-fs02\bfiles$\situation` |
| `/mnt/monitor/ogh-zakazy` | CIFS **read-only**: `\\mggt\work\Common\ОГХ\Заказы` |
| Docker volume `monitor_pgdata` | БД `monitor` |

---

## CIFS-шары (read-only)

Снимок **2026-08-19**. Обе шары смонтированы на хосте **только для чтения**. Collector видит обе через bind `ro` (`rslave`): `/mnt/monitor/ogh-zakazy` и `/mnt/monitor/situation`.

| Параметр | Значение |
|----------|----------|
| Режим | **`ro`** (запись ядром отклоняется) |
| Учётка | `MGGT\srv_opmonitoring` |
| Credentials | `/root/.cifs-opmonitoring` (`chmod 600`, не в git) |
| Пакеты | `cifs-utils`, `keyutils` |
| SMB | `vers=3.0`, `sec=ntlmssp` |
| fstab | `/etc/fstab` (бэкап: `/etc/fstab.bak.monitor-cifs`) |
| Автомонтирование | systemd `x-systemd.automount`, idle-timeout 60 с, `_netdev,nofail` |

| UNC | Локальная точка | Файл-сервер (факт) |
|-----|-----------------|--------------------|
| `\\len-fs02\bfiles$\situation` | `/mnt/monitor/situation` | `len-fs02.mggt` (`172.21.213.12:445`) |
| `\\mggt\work\Common\ОГХ\Заказы` | `/mnt/monitor/ogh-zakazy` | DFS `mggt` (`172.16.15.101`) → `172.21.213.33` |

Юниты (из fstab-generator, `is-enabled=generated`):

- `mnt-monitor-situation.automount` / `.mount`
- `mnt-monitor-ogh\x2dzakazy.automount` / `.mount`

Проверка:

```bash
findmnt /mnt/monitor/situation /mnt/monitor/ogh-zakazy
ls /mnt/monitor/situation | head
ls /mnt/monitor/ogh-zakazy | head
# запись должна падать: Read-only file system
touch /mnt/monitor/situation/.ro_test
```

---

## ogh_order_photo_upload (23:30)

Залив полевых фото заказов ОГХ в MSI Holes `POST /api/upload`.

| Параметр | Значение |
|----------|----------|
| Источник строк | `public.mview_mon_op_prod` (**SELECT only**) |
| Фильтр | `ogno LIKE '12/ОГХ-%'`, `opernm = 'Проверка результатов съемки'`, `edf > 2026-08-15` |
| Фото | `/mnt/monitor/ogh-zakazy/<хвост url после Заказы>/02_Поле/Фото` |
| Инкремент | `genplan.ogh_order_photo_log` (`source_relpath` UNIQUE) |
| Шара | read-only, файлы не удаляются |
| Cron | **23:30** Europe/Moscow (`max_instances=1`) |
| Dry-run | `docker compose exec collector python -m collector.scheduler --run ogh_order_photo_upload_dry` |

Первый live-прогон 2026-08-19: dry-run `rows=68 ok_dirs=63 photos=3106 missing=3 bad_url=2`.

---

## situation_photo_upload (23:00)

Залив фото situation в MSI Holes `POST /api/upload`. Идёт **раньше** `ogh_order_photo_upload` (23:30).

| Параметр | Значение |
|----------|----------|
| Источник строк | `public.mview_mon_op_prod` JOIN `public.mview_mon_op_files` (**SELECT only**) |
| Фильтр | `(ono IS NULL OR ono NOT LIKE '12/ОГХ-%')`, `opernm = 'Проверка результатов съемки'`, `edf > 2026-08-15` |
| Путь | `fnm` от корня `/mnt/monitor/situation` (файл или папка с фото) |
| Инкремент | `genplan.situation_photo_log` (`source_relpath` UNIQUE) |
| Шара | read-only, файлы не удаляются |
| Cron | **23:00** Europe/Moscow (`max_instances=1`) |
| Dry-run | `docker compose exec collector python -m collector.scheduler --run situation_photo_upload_dry` |

Первый live-прогон 2026-08-19: dry-run `prod_rows=129 file_rows=369 photos=369 missing=0 bad_fnm=0`. Live: **369 uploaded, 0 failed**. Заказы: `84/11-26/00043`, `3/ДЖКХ-26/00265`, `СИС-25/00062`.
