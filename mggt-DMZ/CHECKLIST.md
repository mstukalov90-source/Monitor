# Чеклист готовности DMZ — Этап 1

## Подготовка

- [ ] Прочитан [SWEB-SAFETY.md](SWEB-SAFETY.md)
- [ ] SWEB health OK: `curl http://77.222.63.161:8000/health`
- [ ] Backend health OK: `curl http://172.21.198.219:8000/health`
- [ ] Папка `mggt-DMZ/` в репозитории

## Сервер А (DMZ `172.21.198.222`)

- [ ] RED OS, nginx + nginx-mod-stream установлены
- [ ] Конфиг [nginx/nginx.conf](nginx/nginx.conf) развёрнут
- [ ] `nginx -t` — OK
- [ ] `systemctl status nginx` — active
- [ ] `curl http://127.0.0.1:8000/health` на `.222` — OK
- [ ] firewalld настроен ([firewall/server-a-ufw.sh](firewall/server-a-ufw.sh) — firewalld)
- [ ] На DMZ нет Docker, PostgreSQL, `/opt/monitor`

## Сервер Б (Backend `172.21.198.219`)

- [ ] `docker compose ps` — все сервисы Up
- [ ] firewalld настроен ([firewall/server-b-firewalld.sh](firewall/server-b-firewalld.sh))
- [ ] 5432/8000 доступны от `.222`
- [ ] `MONITOR_API_PUBLIC_BASE_URL=http://172.21.198.222:8000` в `.env`
- [ ] API перезапущен: `docker compose up -d api`

## Тесты через DMZ

- [ ] `GET /health` через `.222` — OK
- [ ] `PUT /api/photos/meta/{uuid}` — запись в `genplan.photo_meta` на `.219`
- [ ] `PUT /api/uuids/{uuid}` — OK
- [ ] `POST /api/mggtfield/photos` — файл на `.219` в `mggtfield_photo/`
- [ ] `psql` через `.222:5432` — OK
- [ ] Файлы **не** появляются на `.222`

## SWEB не затронут

- [ ] `curl http://77.222.63.161:8000/health` — по-прежнему OK
- [ ] Контейнеры SWEB `Up` (read-only проверка)
- [ ] `.env` на SWEB **не изменялся**

## Cutover (позже)

- [ ] Потребители уведомлены (docs из [consumers/](consumers/))
- [ ] Внешний IP DMZ назначен (если нужен доступ из интернета)
- [ ] Все клиенты переключены
- [ ] Cron на `.219` стабилен ≥1–2 суток
- [ ] Явное согласование на остановку SWEB
- [ ] SWEB остановлен по [CUTOVER.md](CUTOVER.md)
