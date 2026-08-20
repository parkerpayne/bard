FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pip -U

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
COPY web/ ./web/
COPY .env.example .env.example

ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/app/data/bard.db

RUN mkdir -p /app/data

CMD ["python", "-m", "bot.main"]
