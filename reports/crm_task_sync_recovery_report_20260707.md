# CRM Task Sync Recovery — полный отчёт

**Дата:** 2026-07-07  
**Сервер:** 77.222.63.161 (`/opt/monitor`)  
**Бэкап:** `/opt/monitor/reports/monitor_pre_crm_fix.dump` (156 MB)

---

## 1. Резюме

До восстановления только **14.3%** split-строк data_mos (4205 из 29377) имели `task_key` и связь с `crm.tasks`. Три сервиса (62501, 62441, 62461) были полностью без задач; у всех родителей стоял ложный `tasked=true`, блокировавший geom split.

После выполнения плана: **100%** строк с геометрией имеют `task_key` (**29298**), создано **25093** новых CRM-задач, ложный `tasked` сброшен, ошибок `duplicate task_key` при прогоне не было.

| Метрика | До (baseline) | После (final) |
|---|---:|---:|
| Строк с geom | 29377 | 29298 |
| С `task_key` | 4205 (14.3%) | **29298 (100%)** |
| Пробел (geom без task_key) | 25172 | **0** |
| Ложный `tasked` | 9187 | **0** |
| Duplicate `task_key` | 0 | **0** |
| CRM scoped tasks | 4205 | **29298** |

---

## 2. Выполненные фазы

### Фаза 0 — Подготовка
- Baseline: [reports/crm_task_sync_baseline_20260707.md](crm_task_sync_baseline_20260707.md)
- `pg_dump` на VPS: `reports/monitor_pre_crm_fix.dump`

### Фаза 1 — Исправления кода
- **`_restore_task_key_links`**: привязка через `WHERE id = (SELECT … LIMIT 1)` — устранён duplicate `task_key` при нескольких split-строках с одним `global_id+geom_hash`
- **`_link_split_rows`**: guard `occupied.task_key = ct.key` — не назначать уже занятый ключ
- **`sync_crm_tasks_after_etl`**: `refresh_all_tasked_parents` вместо одностороннего `_mark_tasked_parents`
- **`data_mos_job`**: в message добавлено `crm_sync: inserted=… linked=… tasked_parents=…`
- **sql/31**: одноразовый сброс `tasked` по фактическим `task_key`
- **scripts/crm_task_sync_audit.py**: автоматический аудит

### Фаза 2 — Деплой
- `docker compose up -d --build collector` на VPS
- Применён `sql/31_data_mos_reset_false_tasked.sql`
- После sql/31: `items_62501` — 0 tasked / 7975 not_tasked (сброс ложной заморозки)

### Фаза 3 — ETL (последовательно)

| Job | Статус | crm_sync inserted | crm_sync linked | task_key after |
|---|---|---:|---:|---:|
| data_mos_62501 | success | 23433 | 23433 | 23433 |
| data_mos_62441 | success | 88 | 88 | 88 |
| data_mos_62461 | success | 1087 | 1087 | 1087 |
| data_mos_2855 | success | 485 | 485 | 4690 |

Все 4 job завершились без ошибок. Ошибок `duplicate task_key` не было.

### Фаза 4 — Верификация
- Final audit: [reports/crm_task_sync_final_20260707.md](crm_task_sync_final_20260707.md)
- Критерии приёмки: **все выполнены**

---

## 3. CRM tasks по сервисам (после)

| Колонка | point | line | polygon | total |
|---|---:|---:|---:|---:|
| oati_id (2855) | 1451 | 1982 | 1257 | 4690 |
| earthwork_id (62501) | 8773 | 9579 | 5081 | 23433 |
| localwork_id (62441) | 85 | 0 | 3 | 88 |
| avr_mos_id (62461) | 0 | 614 | 473 | 1087 |
| **Итого** | | | | **29298** |

---

## 4. Duplicate task_key — анализ и результат

### Проблема (до фикса)
При geom split restore по `global_id + geom_hash` один `UPDATE` мог затронуть **несколько** split-строк (GeometryCollection → несколько points с одним `global_id`). Это вызывало:
```
duplicate key value violates unique constraint "items_2855_points_uq_task_key"
```

### Исправление
- Restore: только одна строка на `task_key` (`LIMIT 1`)
- Link: occupied guard на `ct.key`
- Логирование multi-match кандидатов

### Результат прогона 2855
- **0** ошибок duplicate `task_key`
- Множество предупреждений `skip restore task_key … (already occupied)` на polygons — ожидаемо: ключ уже восстановлен на одну строку, вторая получила новую задачу через sync (+485 inserted)
- **0** дублей `task_key` в split-таблицах (проверка audit)

### Multi-match кандидаты (остаются в данных, не баг)
Примеры строк с одним `global_id` и несколькими split-частями — для каждой части теперь отдельная CRM-задача. См. секцию в final audit.

---

## 5. Изменённые файлы (репозиторий)

- `collector/data_mos_geom_split.py`
- `collector/crm_task_sync.py`
- `collector/jobs/data_mos_job.py`
- `sql/31_data_mos_reset_false_tasked.sql`
- `scripts/crm_task_sync_audit.py`
- `tests/test_crm_task_sync.py`
- `tests/test_data_mos_task_key_preserve.py`

---

## 6. Рекомендации на будущее

1. **Ночной `data_mos` (03:00)** — мониторить `collector.job_runs.message` на `crm_sync: inserted=0 linked=0` при ненулевом gap
2. **Не запускать** data_mos jobs параллельно (был deadlock на 62441)
3. **Периодический аудит:** `python scripts/crm_task_sync_audit.py --output reports/audit.md`
4. При сбое ETL — откат из `monitor_pre_crm_fix.dump`

---

## 7. Команды для повторного аудита на VPS

```bash
ssh root@77.222.63.161
cd /opt/monitor
docker compose exec collector python scripts/crm_task_sync_audit.py \
  --title "CRM Task Sync Audit" \
  --output /app/reports/audit.md
```
