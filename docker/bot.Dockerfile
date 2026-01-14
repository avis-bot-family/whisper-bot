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

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Установка зависимостей
WORKDIR $SRC_DIR

RUN pip install --upgrade pip && \
    pip install --no-cache-dir poetry==$POETRY_VERSION

COPY pyproject.toml pyproject.toml

# Создаем виртуальное окружение
RUN poetry env use python3

# Устанавливаем llvmlite через pip с предкомпилированными wheels
# Это избегает необходимости компиляции из исходников с LLVM
# Устанавливаем в виртуальное окружение poetry
RUN poetry run pip install --no-cache-dir llvmlite

# Устанавливаем остальные зависимости через poetry
# Poetry должен использовать уже установленный llvmlite
RUN poetry install --no-root --only main --no-interaction

# Копирования кода приложения
COPY ./src/bot $APP_DIR
