#!/bin/sh
set -eu
mkdir -p "$DATA_DIR"
if [ ! -f "$DATA_DIR/db.sqlite3" ]; then
    cp /app/demo/database.sqlite3 "$DATA_DIR/db.sqlite3.tmp"
    mv "$DATA_DIR/db.sqlite3.tmp" "$DATA_DIR/db.sqlite3"
fi
python manage.py migrate --noinput
if [ ! -f "$DATA_DIR/.demo-ready" ]; then
    python manage.py seed_demo --accounts-only
    touch "$DATA_DIR/.demo-ready"
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 240 --access-logfile -
