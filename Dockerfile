FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY README.md .

RUN mkdir -p /data && chown -R app:app /app /data

USER app

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "from car_watch_bot.config import get_settings; s=get_settings(); raise SystemExit(0 if s.discord_bot_token else 1)"

CMD ["python", "-m", "car_watch_bot.main"]
