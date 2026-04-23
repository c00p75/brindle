# Backend deployment

## Ubuntu droplet (systemd)

```bash
# On the droplet, as root
apt-get update
apt-get install -y python3.12-venv git

# Clone (replace URL with your repo)
mkdir -p /opt && cd /opt
git clone https://github.com/<owner>/trading-bot.git trading-bot
cd trading-bot/backend

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
chown -R www-data:www-data /opt/trading-bot
cp deploy/trading-bot-backend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now trading-bot-backend

# Open firewall
ufw allow 8000/tcp || true

# Verify
curl -s http://127.0.0.1:8000/api/health
```

## Updating

```bash
cd /opt/trading-bot
git pull
cd backend
.venv/bin/pip install -r requirements.txt
systemctl restart trading-bot-backend
```
