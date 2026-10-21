# VPS Deployment Guide — PageRails

## What you need before starting

| Item | Spec | Notes |
|---|---|---|
| VPS | 2 vCPU / 4 GB RAM / 40 GB SSD | Hetzner CX22 (~€5/mo) or DigitalOcean Droplet ($18/mo) |
| OS | Ubuntu 22.04 LTS | The commands below assume this |
| Domain | e.g. `recon.pagecapital.ng` | Point an A record at the VPS IP before running Certbot |
| Git repo | Private GitHub repo | Or transfer files via `scp` if not using git |

---

## Step 1 — Provision the server

SSH in as root, then run these once:

```bash
# Create a non-root deploy user
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # copy your SSH key

# Harden SSH (disable root login, disable password auth)
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload sshd

# Firewall — allow only SSH, HTTP, HTTPS
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# System updates
apt-get update && apt-get upgrade -y
```

---

## Step 2 — Install Docker

```bash
# Switch to the deploy user
su - deploy

# Install Docker (official script)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker deploy
newgrp docker            # reload group without logout

# Verify
docker run --rm hello-world
docker compose version   # must be v2.x
```

---

## Step 3 — Clone the code

```bash
cd /opt
sudo mkdir pagerails && sudo chown deploy:deploy pagerails
cd /opt/pagerails

# If using GitHub:
git clone git@github.com:YOUR_ORG/autopilot.git .

# OR transfer from your Mac:
# scp -r /Users/nonsookoroafor/autopilot/* deploy@YOUR_VPS_IP:/opt/pagerails/
```

---

## Step 4 — Configure environment

```bash
cd /opt/pagerails

# Copy the template and fill in real values
cp .env.production .env
nano .env
```

Set these in `.env`:

```bash
DOMAIN=recon.pagecapital.ng          # ← your actual domain
JWT_SECRET=$(openssl rand -hex 32)   # ← run this, paste the output
CORS_ORIGINS=https://recon.pagecapital.ng

# Change all three passwords before going live
USERS=Obasi Egwu|obasi@pagecapital.ng|YourStrongP@ssword1|maker,Damilola Osifala|damilola@pagecapital.ng|YourStrongP@ssword2|checker,Nonso Okoroafor|nonso@pagecapital.ng|YourStrongP@ssword3|checker
```

---

## Step 5 — Configure Nginx domain

```bash
# Replace YOUR_DOMAIN in the nginx config
sed -i "s/YOUR_DOMAIN/recon.pagecapital.ng/g" nginx/nginx.conf
```

---

## Step 6 — Get SSL certificate (Let's Encrypt)

```bash
# Install Certbot on the host (NOT in Docker — it needs to reach port 80 directly)
sudo apt-get install -y certbot

# Stop anything on port 80 first
sudo ufw allow 80/tcp

# Get certificate (standalone mode — no web server needed yet)
sudo certbot certonly --standalone \
  -d recon.pagecapital.ng \
  --email nonso@pagecapital.ng \
  --agree-tos --no-eff-email

# Copy certs to the nginx/ssl directory that Docker mounts
sudo mkdir -p /opt/pagerails/nginx/ssl
sudo cp /etc/letsencrypt/live/recon.pagecapital.ng/fullchain.pem /opt/pagerails/nginx/ssl/
sudo cp /etc/letsencrypt/live/recon.pagecapital.ng/privkey.pem   /opt/pagerails/nginx/ssl/
sudo chown -R deploy:deploy /opt/pagerails/nginx/ssl

# Auto-renew: Certbot installs a systemd timer; verify it:
sudo systemctl status certbot.timer

# Add a post-renew hook to copy new certs and reload Nginx:
sudo tee /etc/letsencrypt/renewal-hooks/post/copy-to-docker.sh <<'EOF'
#!/bin/bash
cp /etc/letsencrypt/live/recon.pagecapital.ng/fullchain.pem /opt/pagerails/nginx/ssl/
cp /etc/letsencrypt/live/recon.pagecapital.ng/privkey.pem   /opt/pagerails/nginx/ssl/
docker exec pagerails-nginx-1 nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/post/copy-to-docker.sh
```

---

## Step 7 — Create data directory and seed the database

```bash
# Create the persistent volume directory (Docker mounts this)
mkdir -p /opt/pagerails/data/inputs /opt/pagerails/data/outputs \
         /opt/pagerails/data/uploads

# If you have an existing recon.db from development, copy it:
# scp pcg_recon/recon.db deploy@YOUR_VPS_IP:/opt/pagerails/data/recon.db

# If starting fresh — the backend creates it on first run
```

---

## Step 8 — Build and start

```bash
cd /opt/pagerails

# Build all containers (takes 3–5 minutes on first run)
docker compose build --parallel

# Start everything
docker compose up -d

# Watch logs
docker compose logs -f
```

Verify it's running:
```bash
curl https://recon.pagecapital.ng/api/health
# → {"status":"ok","version":"0.1.0"}

curl -X POST https://recon.pagecapital.ng/api/auth/token \
  -d "username=obasi@pagecapital.ng&password=YourStrongP@ssword1" \
  -H "Content-Type: application/x-www-form-urlencoded"
# → {"access_token":"eyJ...","token_type":"bearer",...}
```

Open **https://recon.pagecapital.ng** in a browser — you should see the login page.

---

## Uploading input files

Bank statements and Symplus exports need to be in the right directory on the server. Two options:

**A — Via the web UI (recommended)**
Log in as a maker → Files page → drag-and-drop. Files are stored at `/opt/pagerails/data/inputs/{account_id}/`.

**B — Direct SCP** (for large batches)
```bash
scp "STATEMENT_2026-10.xls" deploy@YOUR_VPS_IP:/opt/pagerails/data/inputs/PAM-PRV-CLIENTS/
```

---

## Running a reconciliation

Once files are uploaded, trigger from the UI (Dashboard → New Run), or via the API:

```bash
TOKEN=$(curl -s -X POST https://recon.pagecapital.ng/api/auth/token \
  -d "username=obasi@pagecapital.ng&password=..." \
  -H "Content-Type: application/x-www-form-urlencoded" | jq -r .access_token)

curl -X POST https://recon.pagecapital.ng/api/runs/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_ids":["PAM-PRV-CLIENTS"],"period":"2026-10","maker":"Obasi Egwu"}'
```

---

## Deploying updates

After pushing new code to git:

```bash
cd /opt/pagerails
bash deploy.sh
```

---

## Backup (set up once)

```bash
chmod +x /opt/pagerails/backup.sh

# Add to crontab (runs at 2am daily)
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/pagerails/backup.sh >> /var/log/pagerails-backup.log 2>&1") | crontab -
```

---

## Monitoring

```bash
# Container status
docker compose ps

# Live logs
docker compose logs -f backend
docker compose logs -f frontend

# Resource usage
docker stats

# Nginx access log
docker compose logs nginx | tail -50

# Database size
du -sh /opt/pagerails/data/recon.db
```

---

## Troubleshooting

| Problem | Check |
|---|---|
| SSL cert error | `sudo certbot certificates` — check expiry |
| Backend 500 | `docker compose logs backend` |
| Blank page | `docker compose logs frontend` |
| Login fails | Check `USERS` in `.env`, check `JWT_SECRET` |
| Run fails | Check `RECON_INPUTS_DIR` path, file permissions |
| Upload fails | Check `UPLOAD_DIR` exists and writable (`ls -la /opt/pagerails/data/uploads/`) |

---

## Recommended VPS providers (for Nigerian teams)

| Provider | Region | Notes |
|---|---|---|
| Hetzner | EU (Frankfurt) | Best value (~€5/mo for CX22), good latency to NG |
| DigitalOcean | NYC / Frankfurt | Easy interface, $18/mo for 2vCPU/4GB |
| AWS Lightsail | Cape Town | Closest AWS to NG, ~$12/mo |
| Azure | South Africa North | Lowest latency option, enterprise support |
