#!/bin/bash
# backup.sh — back up the database and uploaded files to an external location
# Run via cron: 0 2 * * * /opt/pagerails/backup.sh >> /var/log/pagerails-backup.log 2>&1
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/pagerails-backups}"
DATE=$(date +%Y-%m-%d)

mkdir -p "$BACKUP_DIR"

echo "[backup] $DATE — starting"

# Stop writes momentarily for a consistent SQLite snapshot
docker compose exec backend sqlite3 /data/recon.db ".backup /data/pagerails-backup-$DATE.db"
cp /opt/pagerails/data/pagerails-backup-"$DATE".db "$BACKUP_DIR/"
rm /opt/pagerails/data/pagerails-backup-"$DATE".db

# Archive uploads
tar -czf "$BACKUP_DIR/uploads-$DATE.tar.gz" /opt/pagerails/data/uploads/ 2>/dev/null || true

# Keep last 30 days
find "$BACKUP_DIR" -name "pagerails-backup-*.db"    -mtime +30 -delete
find "$BACKUP_DIR" -name "uploads-*.tar.gz"     -mtime +30 -delete

echo "[backup] Done — $(du -sh $BACKUP_DIR)"
