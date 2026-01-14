FROM ubuntu:22.04

# Установка системных зависимостей и очистка кеша в одном слое
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        sudo \
        python3.10 \
        python3-distutils \
        python3-pip \
        ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Переменные окружения и пути
ARG POETRY_VERSION=1.6.1
ENV SRC_DIR=/opt \
    APP_DIR=/opt/bot \
    PYTHONPATH=/opt:/opt/bot \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

WORKDIR $SRC_DIR

# Установка pip и Poetry в одном слое
RUN pip install --no-cache-dir --upgrade pip poetry==$POETRY_VERSION

# Копирование файлов зависимостей (менее часто меняются, чем код)
COPY pyproject.toml poetry.lock* ./

# Установка Python зависимостей и PyTorch в одном слое
RUN poetry install --no-root --only main && \
    poetry run pip install --no-cache-dir torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu124

# Копирование кода приложения в последнюю очередь (чаще всего меняется)
COPY ./src/bot $APP_DIR
