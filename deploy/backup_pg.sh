#!/bin/bash
# Automated PostgreSQL backup for Orderfox
# Runs daily via cron: 0 3 * * * /var/www/orderfox/scripts/backup_pg.sh

BACKUP_DIR="/var/www/orderfox/backups"
DB_NAME="orderfox"
DB_USER="orderfox"
DB_HOST="127.0.0.1"
DATE=$(date +%Y-%m-%d_%H-%M)
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

# Dump with compression
PGPASSWORD=orderfox2026 pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/orderfox_${DATE}.sql.gz"

# Remove backups older than 30 days
find "$BACKUP_DIR" -name "orderfox_*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] Backup completed: orderfox_${DATE}.sql.gz"
