FROM ubuntu:22.04

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    sudo \
    python3.10 \
    python3-distutils \
    python3-pip \
    ffmpeg

ARG POETRY_VERSION=1.6.1
# Основной путь приложения
ENV SRC_DIR=/opt
# Путь до телеграм бота
ENV APP_DIR=$SRC_DIR/bot

ENV PYTHONPATH=$SRC_DIR:$APP_DIR \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

# Установка зависимостей
WORKDIR $SRC_DIR

RUN pip install --upgrade pip && \
    pip install --no-cache-dir poetry==$POETRY_VERSION

COPY pyproject.toml pyproject.toml
RUN poetry install --no-root --only main

# Установка PyTorch с поддержкой CUDA
RUN poetry run pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Копирования кода приложения
COPY ./src/bot $APP_DIR
