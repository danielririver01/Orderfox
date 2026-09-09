#!/bin/bash
# ============================================================
# Orderfox — Auto-deploy script
# Ejecutado en el servidor de producción (Oracle Cloud) por
# GitHub Actions tras un push a `main`.
#
# Flujo: git pull -> deps -> build CSS -> backup BD (si hay
# migraciones pendientes) -> flask db upgrade -> restart -> health check
#
# Uso (desde GitHub Actions):
#   ssh -i <deploy_key> -p <port> ubuntu@<host> "bash -s" < deploy/update_server.sh
#
# Requisitos de una sola vez en el servidor:
#   sudo apt install -y nodejs npm postgresql-client
# (ver deploy/AUTO_DEPLOY.md)
# ============================================================

set -euo pipefail

APP_DIR="/var/www/orderfox"
ENV_FILE="$APP_DIR/.env"
SERVICE="orderfox"
LOG_DIR="/var/log/orderfox"
LOG="$LOG_DIR/deploy.log"
BACKUP_DIR="$LOG_DIR/backups"
BACKUP_RETENTION_DAYS=14
HEALTH_URL="http://127.0.0.1:8000/"
HEALTH_MAX_ATTEMPTS=30   # 30 x 2s = ~60s de espera

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }
fail() { log "ERROR: $*"; exit 1; }

echo "============================================================" >> "$LOG"
log "🚀 Deploy iniciado"

# ── 0. Sanity checks ──────────────────────────────────────────
[ -d "$APP_DIR/.git" ] || fail "No hay repositorio en $APP_DIR. ¿Corriste deploy/setup_server.sh?"
command -v npm >/dev/null 2>&1 || fail "npm no está instalado. Corre: sudo apt install -y nodejs npm"
command -v sudo >/dev/null 2>&1 || fail "sudo no disponible en el servidor"
cd "$APP_DIR"

# ── 1. Actualizar código (rama main) ─────────────────────────
log "[1/6] Actualizando código desde origin/main..."
git fetch --all --prune 2>&1 | tail -1 || true
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    log "      Repo estaba en '$BRANCH' → checkout a main"
    git checkout main 2>&1 | tail -1 || fail "No se pudo hacer checkout a main (¿rama main existe?)"
fi
# Descartar SOLO el artifact de build generado (se regenera en el paso 3).
# Jamás usar stash/clean aquí: borran archivos sin trackear del servidor
# (config de gunicorn, backups de BD, scripts) — así se tiró el sitio el 2026-09-09.
git checkout -- app/static/CSS/output.css 2>/dev/null || true
if ! git merge --ff-only origin/main 2>&1 | tail -2; then
    fail "git pull falló (repo sucio). Revisa: git -C $APP_DIR status"
fi
log "      Commit actual: $(git rev-parse --short HEAD)"

# ── 2. Dependencias Python ────────────────────────────────────
log "[2/6] Instalando dependencias Python..."
.venv/bin/pip install -q -r requirements.txt || fail "pip install falló"

# ── 3. Build CSS (Tailwind) ───────────────────────────────────
log "[3/6] Compilando CSS (Tailwind)..."
npm install --no-audit --no-fund 2>&1 | tail -1 || fail "npm install falló"
npm run build:css 2>&1 | tail -2 || fail "npm run build:css falló"

# ── 4. Migraciones + backup ───────────────────────────────────
log "[4/6] Revisando migraciones pendientes..."
export FLASK_APP=app
export FLASK_ENV=production
CUR=$(.venv/bin/python -m flask db current 2>/dev/null | grep -oE '[0-9a-f]{12}' | head -1 || true)
HEAD=$(.venv/bin/python -m flask db heads  2>/dev/null | grep -oE '[0-9a-f]{12}' | head -1 || true)
log "      current=$CUR  head=$HEAD"

if [ "$CUR" != "$HEAD" ]; then
    log "      Hay migraciones pendientes → backup de BD antes de migrar"
    URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true)
    [ -n "$URL" ] || fail "No se encontró DATABASE_URL en $ENV_FILE"
    mkdir -p "$BACKUP_DIR"

    case "$URL" in
        postgresql*)
            PGURL=$(printf '%s' "$URL" | sed 's/postgresql+psycopg2:/postgresql:/')
            command -v pg_dump >/dev/null 2>&1 || fail "pg_dump no está instalado. Corre: sudo apt install -y postgresql-client"
            BK="$BACKUP_DIR/orderfox_$(date +%Y%m%d_%H%M%S).dump"
            pg_dump "$PGURL" -Fc -f "$BK" || fail "Backup PostgreSQL falló"
            log "      Backup OK: $BK"
            ;;
        mysql*)
            MYSQL_URL=$(printf '%s' "$URL" | sed 's|mysql+pymysql://||')
            MUSER=${MYSQL_URL%%:*}; REST=${MYSQL_URL#*:}
            MPASS=${REST%%@*}; MHP=${REST#*@}
            MHOST=${MHP%%:*}; MPORT=${MHP#*:}; MPORT=${MPORT%%/*}; MDB=${MHP##*/}
            command -v mysqldump >/dev/null 2>&1 || fail "mysqldump no está instalado"
            BK="$BACKUP_DIR/orderfox_$(date +%Y%m%d_%H%M%S).sql.gz"
            mysqldump -h "$MHOST" -P "$MPORT" -u "$MUSER" "-p$MPASS" "$MDB" 2>/dev/null | gzip > "$BK" \
                || fail "Backup MySQL falló"
            log "      Backup OK: $BK"
            ;;
        *)
            fail "Motor de BD no reconocido en DATABASE_URL. Configura el backup manualmente y reintenta."
            ;;
    esac

    # Retención: borrar backups antiguos
    find "$BACKUP_DIR" -type f \( -name '*.dump' -o -name '*.sql.gz' \) -mtime +$BACKUP_RETENTION_DAYS -delete

    log "      Ejecutando flask db upgrade..."
    .venv/bin/python -m flask db upgrade || fail "flask db upgrade falló"
    log "      Migraciones aplicadas ✔"
else
    log "      Sin migraciones pendientes, no se requiere backup"
fi

# ── 5. Reiniciar servicio ─────────────────────────────────────
log "[5/6] Reiniciando servicio $SERVICE..."
sudo systemctl restart "$SERVICE" || fail "systemctl restart $SERVICE falló"

# ── 6. Health check ───────────────────────────────────────────
log "[6/6] Health check en $HEALTH_URL..."
ok=0
for i in $(seq 1 "$HEALTH_MAX_ATTEMPTS"); do
    CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL" || true)
    if [ "$CODE" = "200" ] || [ "$CODE" = "301" ] || [ "$CODE" = "302" ]; then
        ok=1
        break
    fi
    sleep 2
done
if [ "$ok" = "1" ]; then
    log "✅ Deploy completado — HTTP $CODE en $HEALTH_URL"
else
    log "⚠️  El servicio no respondió HTTP 2xx/3xx. Último código: ${CODE:-sin respuesta}"
    sudo systemctl is-active "$SERVICE" || true
    fail "Health check falló — revisa: sudo journalctl -u $SERVICE -n 50"
fi