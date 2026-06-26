FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM node:20-alpine AS css-builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY app/static/CSS/ ./app/static/CSS/
RUN npm run build:css || echo "CSS build skipped"

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --from=css-builder /app/app/static/CSS/output.css ./app/static/CSS/output.css

COPY . .

ENV PYTHONUNBUFFERED=1
ENV FLASK_DEBUG=False

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--timeout", "120", "run:app"]
