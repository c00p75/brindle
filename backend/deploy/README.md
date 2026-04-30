# Backend deployment

## Ubuntu droplet (systemd)

```bash
# On the droplet, as root
apt-get update
apt-get install -y python3.12-venv git

# Clone (replace URL with your repo)
mkdir -p /opt && cd /opt
git clone https://github.com/<owner>/brindle.git brindle
cd brindle/backend

# venv + deps
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Environment
cat > .env <<'EOF'
APP_ENV=production
JWT_SECRET=$(openssl rand -hex 48)
JWT_ALGO=HS256
JWT_EXPIRE_MINUTES=60
PAPER_TRADING_ONLY=true
LIVE_TRADING_ENABLED=false
CORS_ORIGINS=https://<vercel-domain>
EOF
chmod 600 .env

# systemd
chown -R www-data:www-data /opt/brindle
cp deploy/brindle-backend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now brindle-backend

# Open firewall
ufw allow 8000/tcp || true

# Verify
curl -s http://127.0.0.1:8000/api/health
```

## Updating

```bash
cd /opt/brindle
git pull
cd backend
.venv/bin/pip install -r requirements.txt
systemctl restart brindle-backend
```
