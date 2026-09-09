#!/usr/bin/env bash
# Diagnostico rapido de 502 (nginx up, gunicorn down) en Oracle Cloud
set -u

echo "=== 1. Estado del servicio ==="
systemctl status orderfox --no-pager -l | head -25

echo
echo "=== 2. Ultimos logs del servicio (journald) ==="
journalctl -u orderfox -n 40 --no-pager | tail -40

echo
echo "=== 3. Quien escucha en el puerto de gunicorn? ==="
ss -tlnp | grep -E ":8000|:8001" || echo "NADA escuchando en 8000/8001"

echo
echo "=== 4. Ultimo log de deploy ==="
tail -50 /var/log/orderfox/deploy.log 2>/dev/null || echo "sin deploy.log"

echo
echo "=== 5. Ultimo error de la app ==="
tail -30 /var/log/orderfox/error.log 2>/dev/null || echo "sin error.log"

echo
echo "=== 6. Ultimas lineas de nginx error.log ==="
sudo -n tail -30 /var/log/nginx/error.log 2>/dev/null || echo "sin nginx error.log (o sudo requiere password)"

echo
echo "=== 7. Estado del repo en el servidor ==="
cd /var/www/orderfox && git log --oneline -3 && git status --short | head -10

echo
echo "=== 8. .env DATABASE_URL (sin password) ==="
grep -E "^DATABASE_URL" /var/www/orderfox/.env | sed -E 's#://([^:]+):[^@]*@#://\1:***@#'

echo
echo "=== 9. Gunicorn instalado en el venv? ==="
/var/www/orderfox/.venv/bin/gunicorn --version 2>&1 || echo "gunicorn NO instalado"

echo
echo "=== 10. Health check local ==="
curl -s -o /dev/null -w "HTTP %{http_code} en 127.0.0.1:8000/health\n" http://127.0.0.1:8000/health || echo "sin respuesta en :8000"
