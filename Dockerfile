FROM python:3.12-slim

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN pip install --no-cache-dir "poetry==2.2.1"

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root

COPY services ./services

ARG SERVICE_MODULE
ENV SERVICE_MODULE=${SERVICE_MODULE}

CMD ["sh", "-c", "uvicorn ${SERVICE_MODULE}:app --host 0.0.0.0 --port ${PORT}"]
