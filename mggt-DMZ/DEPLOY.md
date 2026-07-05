# Деплой DMZ — пошаговая инструкция

Перед началом прочитайте [SWEB-SAFETY.md](SWEB-SAFETY.md). **SWEB (`77.222.63.161`) не трогаем.**

Работа выполняется на:
- **Сервер А** — `172.21.198.222` (DMZ, Ubuntu 22.04)
- **Сервер Б** — `172.21.198.219` (Backend, RED OS 8.0.2)

---

## Предварительные условия

- [ ] Стек на сервере Б работает: `curl http://172.21.198.219:8000/health` → `{"status":"ok"}`
- [ ] SSH-доступ к `.222` и `.219`
- [ ] SWEB жив: `curl http://77.222.63.161:8000/health` → `{"status":"ok"}`

---

## Часть 1. Nginx на сервере А (DMZ)

### 1.1 Установка

Сервер А — **RED OS 8.x** (не Ubuntu):

```bash
ssh root@172.21.198.222
dnf install -y nginx nginx-mod-stream
```

`nginx-mod-stream` обязателен для TCP-прокси PostgreSQL.

### 1.2 Конфигурация

Скопировать конфиг из репозитория:

```bash
# С Mac (из каталога MONITOR):
scp mggt-DMZ/nginx/nginx.conf root@172.21.198.222:/etc/nginx/nginx.conf
```

Или вручную — см. [nginx/nginx.conf](nginx/nginx.conf) и [nginx/README.md](nginx/README.md).

### 1.3 Проверка и запуск

```bash
nginx -t
systemctl enable nginx
systemctl restart nginx
systemctl status nginx
```

### 1.4 Локальная проверка с сервера А

```bash
curl -s http://127.0.0.1:8000/health
# ожидается: {"status":"ok"}
```

---

## Часть 2. Firewall на сервере А

Оба сервера — RED OS, используется **firewalld**:

```bash
ssh root@172.21.198.222
bash /path/to/mggt-DMZ/firewall/server-a-ufw.sh
```

См. [firewall/server-a-ufw.sh](firewall/server-a-ufw.sh). На этапе внутреннего теста порты 5432/8000 открыты для `172.21.198.0/24`.

---

## Часть 3. Firewall на сервере Б

**Важно:** настраивать **после** того, как nginx на `.222` работает и отвечает на health.

```bash
ssh root@172.21.198.219
bash /path/to/mggt-DMZ/firewall/server-b-firewalld.sh
```

См. [firewall/server-b-firewalld.sh](firewall/server-b-firewalld.sh).

Правила:
- 5432/8000 от `172.21.198.222` (DMZ)
- 5432/8000/22 от `172.21.198.0/24` (VPN/админ, до cutover)
- SWEB не упоминается — маршрута к `.219` у него нет

### Проверка после firewall

```bash
# С сервера А — OK
ssh root@172.21.198.222 'curl -s http://172.21.198.219:8000/health'

# Через DMZ — OK
curl -s http://172.21.198.222:8000/health

# SWEB — по-прежнему OK (не трогали)
curl -s http://77.222.63.161:8000/health
```

---

## Часть 4. Обновить `.env` на сервере Б

Только на `172.21.198.219`, **не на SWEB**:

```bash
ssh root@172.21.198.219
nano /opt/monitor/.env
```

Изменить:

```env
MONITOR_API_PUBLIC_BASE_URL=http://172.21.198.222:8000
```

Когда выдадут внешний IP DMZ — заменить на `http://<DMZ_PUBLIC_IP>:8000`.

Перезапуск API:

```bash
cd /opt/monitor && docker compose up -d api
```

---

## Часть 5. Полное тестирование

См. [TESTING.md](TESTING.md).

---

## Часть 6. Внешний IP (когда выдадут)

1. Назначить внешний IP на сервер А (или DNAT на периметральном firewall)
2. На `.222`: `ufw allow 5432/tcp` и `ufw allow 8000/tcp` (или whitelist IP смежников для :8000)
3. Обновить `MONITOR_API_PUBLIC_BASE_URL` на `.219`
4. Обновить адреса в [consumers/](consumers/)
5. Уведомить потребителей
6. Cutover по [CUTOVER.md](CUTOVER.md)

---

## Откат

| Что откатить | Как |
|--------------|-----|
| nginx на `.222` | `systemctl stop nginx` |
| firewall на `.222` | `ufw disable` или удалить правила |
| firewall на `.219` | `firewall-cmd --reload` с бэкапом зоны |
| `.env` на `.219` | Вернуть предыдущий `MONITOR_API_PUBLIC_BASE_URL` |
| SWEB | Не трогали — продолжает работать |
