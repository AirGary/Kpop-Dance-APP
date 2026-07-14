FROM python:3.13-slim@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY api ./api
RUN python -m pip install --no-cache-dir . \
    && groupadd --system stage-lab \
    && useradd --system --gid stage-lab --home-dir /nonexistent stage-lab

USER stage-lab
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn api.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
