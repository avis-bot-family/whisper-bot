FROM python:3.10-slim

LABEL app=transcribe-worker
LABEL lang=python

ARG POETRY_VERSION=2.2.0

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Основной путь приложения
ENV SRC_DIR=/opt
# Путь до воркера транскрибации
ENV APP_DIR=$SRC_DIR/transcribe_worker

ENV PYTHONPATH=$SRC_DIR \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

# Установка зависимостей
WORKDIR $SRC_DIR

RUN pip install --upgrade pip && \
    pip install --no-cache-dir poetry==$POETRY_VERSION

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main,worker

# Установка PyTorch с поддержкой CUDA
RUN poetry run pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu124

# Копирование кода приложения
COPY ./src/transcribe_worker $APP_DIR

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "transcribe_worker.main:app", "--host", "0.0.0.0", "--port", "8000"]
