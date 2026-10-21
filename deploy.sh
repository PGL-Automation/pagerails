#!/bin/bash
# deploy.sh — pull latest code and restart containers with zero downtime
set -euo pipefail

echo "[deploy] $(date)"

# Pull latest
git pull origin main

# Rebuild only changed services
docker compose build --parallel

# Rolling restart: backend first, then frontend (Nginx stays up throughout)
docker compose up -d --no-deps backend
echo "[deploy] Backend restarted — waiting 5s for health check…"
sleep 5

docker compose up -d --no-deps frontend
echo "[deploy] Frontend restarted."

# Prune old images
docker image prune -f

echo "[deploy] Done. $(docker compose ps --format 'table {{.Name}}\t{{.Status}}')"
