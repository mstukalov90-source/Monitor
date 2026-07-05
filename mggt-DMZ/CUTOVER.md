# Cutover — переключение потребителей и остановка SWEB

**Выполнять только после:**
- Полного прохождения [CHECKLIST.md](CHECKLIST.md)
- Стабильной работы DMZ ≥1–2 суток
- **Явного согласования** на остановку SWEB

До cutover SWEB (`77.222.63.161`) продолжает быть единственным продом для внешних клиентов.

---

## Этап A. Внутренний cutover (VPN / корп. сеть)

Адреса для тестовых потребителей внутри сети:

| Параметр | Значение |
|----------|----------|
| API Base URL | `http://172.21.198.222:8000` |
| PostgreSQL host | `172.21.198.222` |
| PostgreSQL port | `5432` |
| Database | `monitor` |
| User | `monitor` |
| API key | без изменений |

Документация: [consumers/](consumers/)

---

## Этап B. Внешний cutover (когда выдадут внешний IP DMZ)

| Параметр | Было (SWEB) | Стало (DMZ) |
|----------|-------------|-------------|
| API Base URL | `http://77.222.63.161:8000` | `http://<DMZ_PUBLIC_IP>:8000` |
| PostgreSQL host | `77.222.63.161` | `<DMZ_PUBLIC_IP>` |
| PostgreSQL port | `5432` | `5432` |
| API key | — | без изменений |

### Действия администратора

1. Назначить внешний IP на сервер А
2. Открыть порты на firewall DMZ: `5432`, `8000`
3. Обновить на сервере Б:
   ```env
   MONITOR_API_PUBLIC_BASE_URL=http://<DMZ_PUBLIC_IP>:8000
   ```
   ```bash
   cd /opt/monitor && docker compose up -d api
   ```
4. Обновить docs в `mggt-DMZ/consumers/` (заменить `<DMZ_PUBLIC_IP>`)
5. Разослать потребителям новые адреса

### Уведомить потребителей

| Группа | Документ | Что менять |
|--------|----------|------------|
| Смежники (genplan) | [consumers/ONBOARDING-colleagues.md](consumers/ONBOARDING-colleagues.md) | Base URL |
| Android-разработчики | [consumers/ONBOARDING-android.md](consumers/ONBOARDING-android.md) | PG host + API URL |

---

## Этап C. Остановка SWEB

**Только после** подтверждения, что все потребители работают через DMZ.

### Pre-flight

```bash
# DMZ работает
curl -s http://<DMZ_PUBLIC_IP>:8000/health
# или для внутреннего: curl -s http://172.21.198.222:8000/health

# Backend cron стабилен
ssh root@172.21.198.219 'cd /opt/monitor && docker compose exec -T db psql -U monitor -d monitor -c "
SELECT job_name, status, started_at AT TIME ZONE '\''Europe/Moscow'\''
FROM collector.job_runs ORDER BY started_at DESC LIMIT 5;"'

# SWEB ещё жив (перед остановкой)
curl -s http://77.222.63.161:8000/health
```

### Остановка

```bash
ssh -i id_rsa/id_rsa root@77.222.63.161 'cd /opt/monitor && docker compose stop'
```

### Проверка после остановки

```bash
# SWEB недоступен — ожидаемо
curl -s --connect-timeout 3 http://77.222.63.161:8000/health || echo "SWEB stopped OK"

# DMZ работает
curl -s http://<DMZ_PUBLIC_IP>:8000/health
```

---

## Rollback (если что-то пошло не так)

### Вернуть SWEB

```bash
ssh -i id_rsa/id_rsa root@77.222.63.161 'cd /opt/monitor && docker compose up -d'
curl -s http://77.222.63.161:8000/health
```

### Вернуть потребителей на SWEB

| Параметр | Значение |
|----------|----------|
| API Base URL | `http://77.222.63.161:8000` |
| PostgreSQL host | `77.222.63.161` |

Старые docs в `genplan api/` и `mggtfield-photo-api-doc.md` по-прежнему содержат адреса SWEB.

---

## Важно о данных

- Основная БД — на сервере Б (`172.21.198.219`)
- SWEB может содержать устаревшие данные с момента первоначальной миграции
- **Не удалять** данные и контейнеры SWEB минимум 1–2 недели после cutover
- При rollback на SWEB данные, записанные только на `.219` после миграции, на SWEB **не появятся**
