# PROC-01: Runbook de Despliegue a Producción

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Pre-requisitos

### Checklist de Pre-despliegue

- [ ] `npm run build:css` ejecutado (Tailwind compilado a producción)
- [ ] Migraciones de base de datos verificadas localmente
- [ ] Variables de entorno configuradas en `.env` de producción
- [ ] Pruebas unitarias/QA pasadas
- [ ] `AGENTS.md` y documentación actualizados
- [ ] CHANGELOG actualizado con la nueva versión

### Stack de Producción

| Componente | Requisito |
|------------|-----------|
| Servidor | Gunicorn + Nginx (o similar WSGI) |
| Python | 3.11+ |
| MySQL | 8.x con charset utf8mb4 |
| Node.js | 18+ (solo para build de CSS) |
| Dominio | Configurado con SSL/TLS |

---

## 2. Despliegue

### Paso 1: Preparar el servidor

```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependencias del sistema
sudo apt install -y python3 python3-pip python3-venv mysql-server nginx

# Configurar MySQL
sudo mysql_secure_installation
```

### Paso 2: Clonar y configurar el proyecto

```bash
# Clonar repositorio
git clone https://github.com/danielririver01/Orderfox.git /var/www/orderfox
cd /var/www/orderfox

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias Python
pip install -r requirements.txt

# Instalar dependencias Node.js y compilar CSS
npm install
npm run build:css
```

### Paso 3: Configurar variables de entorno

```bash
cp .env.example .env
nano .env   # Editar con valores de producción
```

Variables críticas (ver GUIDE-06 para lista completa):

| Variable | Acción |
|----------|--------|
| `SECRET_KEY` | Generar clave única: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | `mysql+pymysql://user:password@localhost/orderfox` |
| `MAIL_PASSWORD` | Contraseña de aplicación Gmail |
| `CLERK_SECRET_KEY` | Obtener de dashboard de Clerk |
| `MP_ACCESS_TOKEN` | Obtener de dashboard de Mercado Pago |
| `SERVICE_API_KEY` | Generar clave única para Scanner IA |
| `BASE_URL` | URL pública del dominio |
| `FLASK_DEBUG` | `False` |

### Paso 4: Configurar base de datos

```bash
# Crear base de datos
mysql -u root -p
CREATE DATABASE orderfox CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'orderfox'@'localhost' IDENTIFIED BY 'password_seguro';
GRANT ALL PRIVILEGES ON orderfox.* TO 'orderfox'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# Ejecutar migraciones
flask db upgrade
```

### Paso 5: Configurar Gunicorn

```bash
# Probar Gunicorn manualmente
gunicorn --workers 4 --bind 0.0.0.0:8000 "run:app"

# Crear archivo de servicio systemd
sudo nano /etc/systemd/system/orderfox.service
```

```
[Unit]
Description=Orderfox Flask Application
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/orderfox
Environment="PATH=/var/www/orderfox/.venv/bin"
ExecStart=/var/www/orderfox/.venv/bin/gunicorn --workers 4 --bind unix:orderfox.sock -m 007 run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl start orderfox
sudo systemctl enable orderfox
sudo systemctl status orderfox
```

### Paso 6: Configurar Nginx

```bash
sudo nano /etc/nginx/sites-available/orderfox
```

```
server {
    listen 80;
    server_name tudominio.com;

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/orderfox/orderfox.sock;
    }

    location /static/ {
        alias /var/www/orderfox/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /uploads/ {
        alias /var/www/orderfox/app/static/uploads/;
        expires 7d;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/orderfox /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

### Paso 7: Configurar SSL (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tudominio.com
```

---

## 3. Verificación Post-Despliegue

- [ ] Visitar `https://tudominio.com` — debe cargar login
- [ ] Probar login tradicional
- [ ] Probar login con Clerk
- [ ] Verificar que archivos estáticos cargan (`/static/CSS/output.css`)
- [ ] Verificar que las rutas API responden (`/api/products/list`)
- [ ] Verificar base de datos tiene tablas creadas
- [ ] Verificar logs de Gunicorn: `sudo journalctl -u orderfox -f`
- [ ] Verificar logs de Nginx: `sudo tail -f /var/log/nginx/access.log`

---

## 4. Rollback

Si el despliegue falla:

```bash
# 1. Revertir a versión anterior
cd /var/www/orderfox
git checkout <tag-version-anterior>

# 2. Reinstalar dependencias si cambiaron
pip install -r requirements.txt
npm install && npm run build:css

# 3. Revertir base de datos (si hay migraciones nuevas)
flask db downgrade

# 4. Reiniciar servicio
sudo systemctl restart orderfox

# 5. Verificar
sudo systemctl status orderfox
```

---

## 5. Mantenimiento Regular

| Tarea | Frecuencia | Comando |
|-------|------------|---------|
| Limpiar caché de uploads | Mensual | `rm -rf app/static/uploads/*` |
| Respaldar base de datos | Diario | `mysqldump -u root orderfox > backup_$(date +%Y%m%d).sql` |
| Rotar logs | Semanal | Configurar logrotate |
| Revisar espacio en disco | Semanal | `df -h` |
| Actualizar dependencias | Trimestral | `pip list --outdated` |

---

## 6. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
