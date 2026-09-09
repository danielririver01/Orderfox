#!/bin/bash
# Orderfox - Server Setup Script (Oracle Cloud ARM / Ubuntu)
# Run as root or with sudo

set -e

APP_DIR="/var/www/orderfox"
LOG_DIR="/var/log/orderfox"
DOMAIN="${1:-_}"

echo "=== Orderfox Server Setup ==="

# 1. System packages
echo "[1/7] Installing system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git

# 2. Create directories
echo "[2/7] Creating directories..."
sudo mkdir -p $APP_DIR $LOG_DIR
sudo chown -R ubuntu:ubuntu $APP_DIR $LOG_DIR

# 3. Clone repo (if not exists)
if [ ! -d "$APP_DIR/.git" ]; then
    echo "[3/7] Cloning repository..."
    sudo -u ubuntu git clone https://github.com/TU_USUARIO/orderfox.git $APP_DIR
else
    echo "[3/7] Repository already exists, pulling..."
    sudo -u ubuntu git -C $APP_DIR pull
fi

# 4. Python venv + dependencies
echo "[4/7] Setting up Python environment..."
if [ ! -d "$APP_DIR/.venv" ]; then
    sudo -u ubuntu python3 -m venv $APP_DIR/.venv
fi
sudo -u ubuntu $APP_DIR/.venv/bin/pip install --upgrade pip
sudo -u ubuntu $APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt
sudo -u ubuntu $APP_DIR/.venv/bin/pip install gunicorn

# 5. .env file
if [ ! -f "$APP_DIR/.env" ]; then
    echo "[5/7] Creating .env template..."
    sudo -u ubuntu cat > $APP_DIR/.env << 'EOF'
# Flask
SECRET_KEY=CHANGE_ME_TO_RANDOM_STRING
FLASK_ENV=production

# Database (Supabase PostgreSQL)
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@YOUR_HOST:5432/postgres

# Clerk Auth
CLERK_SECRET_KEY=your_clerk_secret
CLERK_PUBLISHABLE_KEY=your_clerk_publishable

# DeepSeek (Copilot)
DEEPSEEK_API_KEY=your_deepseek_key

# Cloudinary
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret

# Other
SCANNER_IA_URL=http://localhost:5000
EOF
    echo "  ⚠️  Edit $APP_DIR/.env with your real values!"
else
    echo "[5/7] .env already exists"
fi

# 6. Systemd service
echo "[6/7] Configuring systemd service..."
sudo cp $APP_DIR/deploy/systemd/orderfox.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable orderfox
sudo systemctl restart orderfox

# 7. Nginx
echo "[7/7] Configuring Nginx..."
sudo cp $APP_DIR/deploy/nginx/orderfox.conf /etc/nginx/sites-available/orderfox
sudo ln -sf /etc/nginx/sites-available/orderfox /etc/nginx/sites-enabled/orderfox
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo ""
echo "=== Setup Complete ==="
echo "App running at: http://$(curl -s ifconfig.me)"
echo ""
echo "Next steps:"
echo "  1. Edit $APP_DIR/.env with your credentials"
echo "  2. sudo systemctl restart orderfox"
echo "  3. (Optional) Run: sudo certbot --nginx -d $DOMAIN"
