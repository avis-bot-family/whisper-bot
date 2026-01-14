# Whisper Bot - Telegram бот для транскрибации аудио и видео

Telegram бот для транскрибации голосовых сообщений, аудио и видео файлов с использованием OpenAI Whisper.

# TODO:

1. большое сообщение не отправляется
- ping-pong-bot  | 2026-01-14 17:35:06.125 | INFO     | bot.utils.transcribe:_transcribe_audio_sync:17 - Модель: medium, Язык: Russian, Устройство: cuda
ping-pong-bot  | 2026-01-14 17:35:06.126 | INFO     | bot.utils.transcribe:_transcribe_audio_sync:22 - Очищен кеш CUDA


ping-pong-bot  | 2026-01-14 17:35:55.074 | INFO     | bot.utils.transcribe:_transcribe_audio_sync:37 - Транскрибация завершена успешно
ping-pong-bot  | 2026-01-14 17:35:55.151 | ERROR    | bot.handlers.transcribe:safe_answer:53 - Ошибка при отправке сообщения: Telegram server says - Bad Request: message is too long
ping-pong-bot  | 2026-01-14 17:35:55.151 | INFO     | bot.handlers.transcribe:transcribe_handler:223 - Транскрибация завершена для файла 2025-09-15_11-02-59.mkv

2. большой файл не обрабатывается

ping-pong-bot  | 2026-01-14 17:32:43.158 | ERROR    | bot.handlers.transcribe:transcribe_handler:228 - Ошибка при обработке файла: Telegram server says - Bad Request: file is too big

## Возможности

- 🎙️ Транскрибация голосовых сообщений
- 🎵 Распознавание речи в аудио файлах
- 🎬 Извлечение текста из видео
- 🚀 Поддержка множества форматов (MP3, WAV, MP4, MKV и др.)
- ⚡ Работа на CPU или GPU (CUDA)

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

#### macOS

```bash
brew install llvm ffmpeg
```

#### Windows

Установите через [LLVM releases](https://github.com/llvm/llvm-project/releases) и добавьте в PATH.

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
transcribe_AUDIO_FILE_PATH=
transcribe_MODEL=medium
transcribe_LANGUAGE=Russian
transcribe_DEVICE=cpu
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
