# The API. Runs migrations, then serves on $PORT (Railway, Render and Fly set it).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY vaani_agent ./vaani_agent
COPY migrations ./migrations
RUN pip install --no-cache-dir .

EXPOSE 8000
# --proxy-headers: behind the platform's proxy, use the caller's real IP (rate limits).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
