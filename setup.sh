#!/bin/bash
# PageRails — Mac Mini setup script
# Run once from the autopilot directory: bash setup.sh
# Takes about 5–10 minutes depending on internet speed.

set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${YELLOW}▸${NC} $1"; }

echo ""; echo "  PageRails — setup"; echo "  ──────────────────"; echo ""

# ── 1. Homebrew ───────────────────────────────────────────────────────────────
info "Checking Homebrew..."
if ! command -v brew &>/dev/null; then
  info "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
fi
ok "Homebrew ready"

# ── 2. Python 3.12 ────────────────────────────────────────────────────────────
info "Checking Python 3.12..."
if ! command -v python3.12 &>/dev/null; then brew install python@3.12; fi
ok "Python $(python3.12 --version | cut -d' ' -f2) ready"

# ── 3. Node.js ────────────────────────────────────────────────────────────────
info "Checking Node.js..."
if ! command -v node &>/dev/null; then brew install node; fi
ok "Node $(node --version) ready"

# ── 4. PM2 ────────────────────────────────────────────────────────────────────
info "Checking PM2..."
if ! command -v pm2 &>/dev/null; then npm install -g pm2; fi
ok "PM2 ready"

# ── 5. Python virtual environment ─────────────────────────────────────────────
info "Setting up Python environment..."
if [ ! -d "$REPO/.venv" ]; then python3.12 -m venv "$REPO/.venv"; fi
source "$REPO/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -e "$REPO/backend/"
pip install --quiet -e "$REPO/pcg_recon/"
ok "Python environment ready"

# ── 6. Frontend ────────────────────────────────────────────────────────────────
info "Installing frontend dependencies..."
cd "$REPO/frontend"
npm install --silent
info "Building frontend (about 2 minutes)..."
npm run build
cd "$REPO"
ok "Frontend built"

# ── 7. Environment file check ─────────────────────────────────────────────────
if [ ! -f "$REPO/backend/.env" ]; then
  JWT_SECRET=$(python3.12 -c "import secrets; print(secrets.token_hex(32))")
  cat > "$REPO/backend/.env" << ENV
RECON_DB_PATH=../pcg_recon/recon.db
RECON_INPUTS_DIR=../pcg_recon/samples/inputs
RECON_CONFIG_DIR=../pcg_recon/config
RECON_OUTPUTS_DIR=../pcg_recon/samples/output
UPLOAD_DIR=./uploads
JWT_SECRET=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
CORS_ORIGINS=http://localhost:3000
PAGEOS_MSGRAPH_CLIENT_ID=7f0c1881-c644-45eb-906c-438e96c8d6dc
PAGEOS_MSGRAPH_TENANT_ID=c5367046-962e-4f7c-bea6-24fa415cd319
PAGEOS_MSGRAPH_CLIENT_SECRET=PASTE_SECRET_HERE
PAGEOS_APPROVALS_EMAIL_USER=approvals@pageaml.com
STATEMENT_IMAP_USER=bankstatements@pageaml.com
PAGERAILS_SIGNATURE_DIR=${REPO}/signatures
FRONTEND_URL=http://localhost:3000
ENV
  echo ""
  echo -e "${YELLOW}  ⚠  backend/.env created — open it and replace PASTE_SECRET_HERE${NC}"
  echo "     with the Microsoft Graph client secret, then run this script again."
  echo "     File: $REPO/backend/.env"
  echo ""
  exit 0
fi

# Check the secret has been filled in
if grep -q "PASTE_SECRET_HERE" "$REPO/backend/.env"; then
  echo -e "${YELLOW}  ⚠  Open backend/.env and replace PASTE_SECRET_HERE with the real secret.${NC}"
  exit 0
fi
ok "backend/.env present"

# ── 8. Signatures ──────────────────────────────────────────────────────────────
mkdir -p "$REPO/signatures"
if [ -z "$(ls -A "$REPO/signatures" 2>/dev/null)" ]; then
  echo ""
  echo -e "${YELLOW}  ⚠  No signatures found at $REPO/signatures/${NC}"
  echo "     Copy these four files there:"
  echo "     signatory_1.jpg  (Toyin Akinde)"
  echo "     signatory_2.png  (Deremi Ogunsipe)"
  echo "     nike_signature.jpg"
  echo "     segun_signature.jpg"
  echo "     Then re-run this script."
  echo ""
  exit 0
fi
ok "Signature files found"

# ── 9. Database ────────────────────────────────────────────────────────────────
info "Initialising database..."
source "$REPO/.venv/bin/activate"

python3 - << 'PYEOF'
import sys
sys.path.insert(0, 'backend')
sys.path.insert(0, 'pcg_recon')
from app import db
db.migrate()
print("  Migrations applied")
PYEOF

python3 scripts/add_payout_users.py
python3 scripts/load_beneficiaries.py

python3 - << 'PYEOF'
import sys
sys.path.insert(0, 'backend')
sys.path.insert(0, 'pcg_recon')
from app import db
from datetime import datetime, timezone
now = datetime.now(timezone.utc).isoformat(timespec='seconds')
with db.get_db() as con:
    for u, c in [
        ('olawunmi.oladigbo@pageaml.com', 'udochukwu.okigbo@pageaml.com'),
        ('toyin.akinde@pageaml.com',      'adenike.odesanya@pageaml.com'),
    ]:
        con.execute(
            'INSERT OR REPLACE INTO stand_ins (user_email, cover_email, updated_at) VALUES (?,?,?)',
            (u, c, now)
        )
print("  Stand-ins configured")
PYEOF

ok "Database ready"

# ── 10. Start with PM2 ─────────────────────────────────────────────────────────
info "Starting services..."
pm2 start "$REPO/pm2.config.js"
pm2 save
ok "Services started"

# ── 11. Auto-start on login ────────────────────────────────────────────────────
info "Configuring auto-start..."
STARTUP_CMD=$(pm2 startup 2>&1 | grep "sudo" | head -1)
if [ -n "$STARTUP_CMD" ]; then
  echo ""
  echo -e "${YELLOW}  Run this one final command to enable auto-start on boot:${NC}"
  echo ""
  echo "  $STARTUP_CMD"
  echo ""
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "  ┌──────────────────────────────────────────────┐"
echo "  │  PageRails is running                        │"
echo "  │                                              │"
echo "  │  Browser:   http://localhost:3000            │"
echo "  │  API docs:  http://localhost:8000/docs       │"
echo "  │                                              │"
echo "  │  pm2 status        check services            │"
echo "  │  pm2 logs          view logs                 │"
echo "  │  pm2 restart all   restart after update      │"
echo "  └──────────────────────────────────────────────┘"
echo ""
echo "  Initial password for all users: PageOS2026!"
echo "  Each user sets their PIN at http://localhost:3000/pin-setup"
echo ""
