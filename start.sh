#!/bin/bash
set -e

echo "Running database migrations..."
python -m flask db upgrade

echo "Starting gunicorn..."
exec gunicorn --bind 0.0.0.0:5000 --workers 3 --timeout 120 run:app
