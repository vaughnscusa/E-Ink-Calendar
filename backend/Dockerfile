FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# DejaVu Sans is the first font in your CSS stack
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Installing Chromium through the same playwright version keeps browser and library in sync
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# One worker; your render lock already serializes screenshots
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 120 server:app
