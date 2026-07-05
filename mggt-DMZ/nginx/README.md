# Nginx на сервере А (DMZ)

Ubuntu 22.04, без Docker.

## Установка

### Ubuntu 22.04

```bash
apt update && apt install -y nginx
```

### RED OS 8.x (текущий сервер А)

```bash
dnf install -y nginx nginx-mod-stream
```

Конфиг включает `include /usr/share/nginx/modules/*.conf;` для TCP stream.

## Развёртывание конфига

```bash
# Бэкап оригинала
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak.$(date +%Y%m%d)

# Скопировать из репозитория MONITOR
cp mggt-DMZ/nginx/nginx.conf /etc/nginx/nginx.conf

nginx -t
systemctl enable nginx
systemctl restart nginx
```

## Проверка

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok"}

ss -tlnp | grep -E '5432|8000'
# nginx слушает оба порта
```

## Что проксируется

| Вход (DMZ) | Backend | Протокол |
|------------|---------|----------|
| `:5432` | `172.21.198.219:5432` | TCP (stream) |
| `:8000` | `172.21.198.219:8000` | HTTP (reverse proxy) |

## Загрузка фото

`client_max_body_size 25m` — лимит чуть выше 20 MiB API.

`proxy_request_buffering off` и `proxy_buffering off` — тело запроса не буферизуется на диск DMZ, идёт транзитом на backend.

## Логи

```bash
tail -f /var/log/nginx/monitor_api_access.log
tail -f /var/log/nginx/monitor_api_error.log
```

## Откат

```bash
cp /etc/nginx/nginx.conf.bak.* /etc/nginx/nginx.conf
systemctl restart nginx
```
