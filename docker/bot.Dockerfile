FROM python:3.12-slim

LABEL app=whisper-bot
LABEL lang=python

ARG POETRY_VERSION=2.2.0

RUN apt-get update && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Основной путь приложения
ENV SRC_DIR=/opt
# Путь до телеграм бота
ENV APP_DIR=$SRC_DIR/bot

ENV PYTHONPATH=$SRC_DIR \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

# Установка зависимостей
WORKDIR $SRC_DIR

RUN pip install --upgrade pip && \
    pip install --no-cache-dir poetry==$POETRY_VERSION

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main,bot

# Копирование кода приложения
COPY ./src/bot $APP_DIR
