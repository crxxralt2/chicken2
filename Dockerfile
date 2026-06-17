FROM python:3.12-slim

WORKDIR /app

# Install ffmpeg and dependencies needed for audio playback
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

ENV PORT=5000
EXPOSE 5000

CMD ["sh", "-c", "uvicorn src.web:app --host 0.0.0.0 --port $PORT"]
