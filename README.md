# Whisper Bot - Telegram бот для транскрибации аудио и видео

Telegram бот для транскрибации голосовых сообщений, аудио и видео файлов с использованием OpenAI Whisper.

## Установка

### Системные требования

Для локальной установки требуется:

- Python 3.12+
- LLVM (для сборки llvmlite)
- FFmpeg (для обработки аудио/видео)

#### Ubuntu/Debian

```bash
sudo apt-get update
sudo apt-get install -y build-essential llvm llvm-dev ffmpeg
```

### Установка зависимостей

```bash
# Установка Poetry (если не установлен)
curl -sSL https://install.python-poetry.org | python3 -

# Установка зависимостей проекта
poetry install
```

### Настройка

Создайте файл `.env` в корне проекта:

```env
bot_TOKEN=your_telegram_bot_token
transcribe_ENABLE_ON_STARTUP=false
transcribe_AUDIO_FILE_PATH=src/bot/audio/privet-druzya.mp3
transcribe_MODEL=medium
transcribe_LANGUAGE=Russian
transcribe_DEVICE=cpu
# Диаризация (pyannote): HF_TOKEN, DIARIZE_BY_DEFAULT, DIARIZE_MIN/MAX_SPEAKERS
transcribe_HF_TOKEN=your_huggingface_token
transcribe_DIARIZE_BY_DEFAULT=true
transcribe_DIARIZE_MIN_SPEAKERS=2
transcribe_DIARIZE_MAX_SPEAKERS=5
```

## Запуск

### Локальный запуск

```bash
withenv ./.env poetry run python3 ./src/bot/main.py
```

### Docker

```bash
docker-compose -f docker/dev.docker-compose.yml up --build
```

## Транскрибация локальных файлов

Скрипт для транскрибации аудио/видео без Telegram:

```bash
# Транскрибация файла по умолчанию (src/bot/audio/privet-druzya.mp3)
poetry run python src/scripts/transcribe_local.py

# Транскрибация указанного файла
poetry run python src/scripts/transcribe_local.py path/to/audio.mp3

# С таймкодами по сегментам
poetry run python src/scripts/transcribe_local.py --timestamps

# Дополнительные опции: --model, --language, --device
poetry run python src/scripts/transcribe_local.py --help
```

### Транскрибация с диаризацией спикеров

**В боте:** команда `/transcribe_diarize` — отправьте аудио/видео для транскрибации с определением спикеров.

**Локальный скрипт:**
```bash
# Требуется HF_TOKEN в .env (примите условия pyannote)
poetry run python src/scripts/transcribe_diarize_local.py --diarize path/to/meeting.mp3
```

Настройка: добавьте в `.env` токен HuggingFace и примите условия модели:
- `transcribe_HF_TOKEN=ваш_токен`
- https://huggingface.co/pyannote/speaker-diarization-community-1

## Использование

1. Отправьте боту голосовое сообщение
2. Или отправьте аудио/видео файл
3. Бот автоматически распознает речь и вернет текст

### Команды

- `/start` - Начать работу с ботом
- `/help` - Справка и информация о боте
- `/transcribe` - Инструкции по транскрибации

## Поддерживаемые форматы

### Аудио
OGG, MP3, WAV, M4A, FLAC, AAC

### Видео
MP4, MKV, AVI, MOV, WEBM, FLV

## Разработка

Проект использует:
- [aiogram](https://github.com/aiogram/aiogram) - асинхронный фреймворк для Telegram Bot API
- [OpenAI Whisper](https://github.com/openai/whisper) - модель распознавания речи
- [Poetry](https://python-poetry.org/) - управление зависимостями
