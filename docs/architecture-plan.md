# Архитектурный план: от монолита к микросервисам

## MVP (текущий фокус)

### Решения для MVP

| Аспект | Выбор | Обоснование |
|--------|-------|-------------|
| **Хранение файлов** | Shared volume | Простота, один сервер, быстрый старт |
| **Очередь задач** | Redis Streams | Consumer groups, retry, масштабирование воркеров |
| **ClickHouse** | Пока нет | Отложено на следующий этап |
| **PostgreSQL** | Пока нет | Отложено на следующий этап |

---

## Этап 1: Вынос транскрибации в отдельный worker

### Цель

Разделить лёгкий Telegram-бот и тяжёлый ML-код (Whisper + pyannote). Обновлять Python и зависимости бота независимо от worker.

### Компоненты

1. **bot-service** (лёгкий)
   - aiogram, pydantic-settings, redis
   - Python 3.12+
   - Скачивает файлы → пишет в shared volume → публикует задачу в Redis Streams

2. **transcribe-worker** (тяжёлый)
   - whisper, pyannote-audio, torch, redis
   - Python 3.10 (ограничения whisper/pyannote)
   - Читает задачи из Redis Streams → обрабатывает → публикует результат

3. **Shared volume**
   - Путь: `/data/tasks/{task_id}/audio.{ext}`
   - Бот пишет файл после скачивания
   - Worker читает файл, после обработки может удалить (опционально)

### Формат сообщений (Redis Streams)

**Stream: `transcribe:tasks`**

```json
{
  "task_id": "uuid-v4",
  "file_path": "/data/tasks/uuid/audio.mp3",
  "diarize": true,
  "model": "medium",
  "language": "Russian",
  "chat_id": 123456,
  "message_id": 789,
  "user_id": 111
}
```

**Stream: `transcribe:results`** (или `result:{task_id}` для point-to-point)

```json
{
  "task_id": "uuid-v4",
  "status": "success",
  "text": "полный текст...",
  "segments": [{"start": 0.0, "end": 2.5, "text": "...", "speaker": "SPEAKER_00"}],
  "error": null
}
```

При ошибке:

```json
{
  "task_id": "uuid-v4",
  "status": "error",
  "text": null,
  "segments": null,
  "error": "описание ошибки"
}
```

### Поток данных

1. Пользователь отправляет аудио → бот
2. Бот скачивает в `/data/tasks/{task_id}/audio.ext`
3. Бот: `XADD transcribe:tasks * task_id ... file_path ...`
4. Бот: подписывается на `transcribe:results` (фильтр по task_id) или блокирующее чтение
5. Worker: `XREADGROUP GROUP transcribe-workers consumer-1 STREAMS transcribe:tasks 0`
6. Worker: обрабатывает файл, публикует `XADD transcribe:results * task_id ...`
7. Бот получает результат → отправляет пользователю

---

## Этап 2: Redis Streams как брокер

### Конфигурация

- Stream `transcribe:tasks` — очередь задач
- Stream `transcribe:results` — результаты (consumer по task_id)
- Consumer group: `transcribe-workers` для распределения нагрузки

### Альтернатива: результат по task_id

Вместо одного stream результатов — отдельный stream/ключ на задачу:

- `XADD result:{task_id} * ...` — worker пишет результат
- Бот: `XREAD STREAMS result:{task_id} 0` с блокировкой и таймаутом

Плюс: бот не фильтрует чужие результаты. Минус: много ключей, нужна очистка (TTL или ручное удаление).

**Рекомендация для MVP:** один stream `transcribe:results`, бот читает с фильтром по task_id в цикле (или отдельный consumer на боте).

---

## Этап 3 (будущее): ClickHouse

### Назначение

- Хранение всех сообщений
- События обработки (старт, завершение, ошибки)
- Аналитика: объёмы, задержки, популярные модели

### Таблицы (черновик)

- `messages` — входящие сообщения
- `transcribe_jobs` — задачи транскрибации
- `transcribe_events` — события (started, completed, failed)

---

## Этап 4 (будущее): PostgreSQL

### Назначение

- Настройки бота (ключ-значение или JSON)
- Настройки пользователей
- Audit log для админ-панели

---

## Этап 5 (будущее): Admin-панель (FastAPI + SQLAdmin)

### Назначение

- Управление настройками
- Просмотр логов и метрик
- CRUD для конфигурации

---

## Структура проекта (после Этапа 1–2)

```
whisper-bot/
├── src/
│   ├── bot/              # Telegram-бот (лёгкий)
│   └── transcribe_worker/  # Worker (отдельный пакет или подпапка)
├── docker/
│   ├── bot.Dockerfile
│   └── worker.Dockerfile
├── docker-compose.yml
├── docs/
│   └── architecture-plan.md  # этот файл
└── ...
```

### docker-compose (MVP)

```yaml
services:
  redis:
    image: redis:7-alpine
    ...

  bot:
    build: ...
    volumes:
      - transcribe_data:/data/tasks
    depends_on: [redis]

  transcribe-worker:
    build: ...
    volumes:
      - transcribe_data:/data/tasks
    depends_on: [redis]

volumes:
  transcribe_data:
```

---

## Открытые вопросы (для следующих итераций)

1. **Таймаут ожидания** — 30 мин? 1 час? Поведение при таймауте (повтор, уведомление пользователю)?
2. **Retry при ошибке worker** — автоматический retry, dead letter queue?
3. **Масштабирование** — несколько воркеров, GPU vs CPU?
4. **Очистка файлов** — удалять ли аудио после обработки? Политика TTL для `/data/tasks/`?
