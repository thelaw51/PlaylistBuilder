FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements before app code so this layer is cached until deps change
COPY requirements.txt .
RUN pip install --no-cache-dir yt-dlp beets -r requirements.txt

COPY . .
COPY docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV FLASK_APP=run.py \
    PYTHONUNBUFFERED=1

EXPOSE 5000
ENTRYPOINT ["entrypoint.sh"]
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:5000", "run:app"]
