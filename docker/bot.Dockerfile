FROM python:3.12-slim

ARG POETRY_VERSION=1.6.1

# Основной путь приложения
ENV SRC_DIR=/opt

# Путь до приложения
ENV APP_DIR=$SRC_DIR/bot

ENV PYTHONPATH=$SRC_DIR \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

# Установка зависимостей
WORKDIR $SRC_DIR

RUN pip install --upgrade pip && \
    pip install --no-cache-dir poetry==$POETRY_VERSION

COPY pyproject.toml pyproject.toml
RUN poetry install --no-root --only main

# Копирования кода приложения
COPY ./src/bot $APP_DIR
