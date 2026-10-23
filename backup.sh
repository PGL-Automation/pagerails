#!/bin/bash
# backup.sh — back up the database and uploaded files to an external location
# Run via cron: 0 2 * * * /opt/pagerails/backup.sh >> /var/log/pagerails-backup.log 2>&1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_PATH="${SCRIPT_DIR}/pcg_recon/recon.db"
UPLOADS_PATH="${SCRIPT_DIR}/backend/uploads"
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/backups}"
DATE=$(date +%Y-%m-%d)

mkdir -p "$BACKUP_DIR"

echo "[backup] $DATE — starting"

# Consistent SQLite snapshot using the built-in .backup command
sqlite3 "$DB_PATH" ".backup ${BACKUP_DIR}/pagerails-backup-${DATE}.db"

# Archive uploads
tar -czf "$BACKUP_DIR/uploads-$DATE.tar.gz" "$UPLOADS_PATH" 2>/dev/null || true

# Keep last 30 days
find "$BACKUP_DIR" -name "pagerails-backup-*.db"    -mtime +30 -delete
find "$BACKUP_DIR" -name "uploads-*.tar.gz"     -mtime +30 -delete

echo "[backup] Done — $(du -sh $BACKUP_DIR)"
