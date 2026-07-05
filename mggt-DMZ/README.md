# MONITOR — миграция в архитектуру DMZ (Этап 1)

Документация и конфиги для переноса MONITOR в двухузловую схему **DMZ + Backend**.

## Серверы

| Имя | IP | Hostname | Роль |
|-----|-----|----------|------|
| **Сервер А (DMZ)** | `172.21.198.222` | `LEN-MONSTRRAB-01P` | nginx-прокси (TCP :5432, HTTP :8000), без БД и файлов |
| **Сервер Б (Backend)** | `172.21.198.219` | `LEN-MOSTRRAB-DCR-01P` | PostgreSQL, API, collector, файловое хранилище |
| **SWEB (текущий прод)** | `77.222.63.161` | — | Работает до cutover — **не трогать** |

Путь проекта на сервере Б: `/opt/monitor`

## Текущий статус

- Стек на сервере Б развёрнут и работает (см. [acses_status.md](../acses_status.md))
- DMZ-прокси на сервере А — настраивается по этой документации
- SWEB продолжает обслуживать внешних потребителей до явного cutover

## Адреса для потребителей

| Этап | API Base URL | PostgreSQL host |
|------|--------------|-----------------|
| Сейчас (прод) | `http://77.222.63.161:8000` | `77.222.63.161` |
| Внутренний тест DMZ | `http://172.21.198.222:8000` | `172.21.198.222` |
| После выдачи внешнего IP | `http://<DMZ_PUBLIC_IP>:8000` | `<DMZ_PUBLIC_IP>` |

API-ключ (`MONITOR_API_KEY`) — **без изменений** при переезде.

## Содержание папки

| Файл | Назначение |
|------|------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Схема, порты, потоки данных |
| [SWEB-SAFETY.md](SWEB-SAFETY.md) | Правила: не повредить SWEB |
| [DEPLOY.md](DEPLOY.md) | Пошаговый деплой DMZ |
| [TESTING.md](TESTING.md) | Проверки через `.222` |
| [CHECKLIST.md](CHECKLIST.md) | Чеклист готовности |
| [CUTOVER.md](CUTOVER.md) | Переключение потребителей и остановка SWEB |
| [nginx/](nginx/) | Конфиг nginx для сервера А |
| [firewall/](firewall/) | Скрипты firewall для А и Б |
| [consumers/](consumers/) | Инструкции для смежников и Android |

## Быстрый старт (администратор)

1. Прочитать [SWEB-SAFETY.md](SWEB-SAFETY.md)
2. Установить nginx на `172.21.198.222` — [nginx/README.md](nginx/README.md)
3. Настроить firewall — [firewall/](firewall/)
4. Прогнать тесты — [TESTING.md](TESTING.md)
5. Cutover — только по [CUTOVER.md](CUTOVER.md)

## API endpoints (проксируются через DMZ)

| Метод | Путь | Потребитель |
|-------|------|-------------|
| `GET` | `/health` | мониторинг |
| `PUT` | `/api/photos/meta/{uuid}` | смежники (genplan meta) |
| `PUT` | `/api/uuids/{uuid}` | смежники (uuid) |
| `POST` | `/api/mggtfield/photos` | Android (загрузка фото) |

PostgreSQL `:5432` — прямое подключение Android-приложения (TCP-прокси).
