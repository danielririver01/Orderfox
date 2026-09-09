# Auto-deploy: git push → Oracle Cloud

Cada `git push` a `main` actualiza automáticamente el servidor de producción:

```
git push origin main
      │
      ▼
GitHub Actions (CI: tests + lint)  ── pasa ──►  job `deploy`
                                                  │  SSH (puerto 22)
                                                  ▼
                                        Oracle Cloud (orderfox.service)
                                        deploy/update_server.sh:
                                        git pull → deps → build CSS →
                                        backup BD → flask db upgrade →
                                        restart → health check
```

- **Solo en `main`**: pushes a `develop` o PRs **no** despliegan.
- **Solo si CI pasa**: si los tests o el lint fallan, no se despliega.
- **Migrations automáticas con backup**: si hay migraciones pendientes, se hace `pg_dump`/`mysqldump` de producción antes de `flask db upgrade` (backups en `/var/log/orderfox/backups/`, retención 14 días).
- **`.env` intacto**: el deploy nunca toca `/var/www/orderfox/.env` (está en `.gitignore` y vive solo en el servidor).

---

## 1. Preparación del servidor (una sola vez)

```bash
# Conectarse por SSH a Oracle Cloud
ssh ubuntu@TU_IP

# Dependencias que el deploy necesita
sudo apt install -y nodejs npm postgresql-client

# Verificar que ubuntu puede reiniciar el servicio sin contraseña
sudo -n true && echo "sudo sin password OK"
# (por defecto en Oracle Cloud Ubuntu ya es así; si no, agregar NOPASSWD en sudoers)
```

> El script usa `pg_dump` para el backup si tu `DATABASE_URL` es PostgreSQL, o
> `mysqldump` si es MySQL. Si tu base es Supabase/managed, `pg_dump` debe poder
> alcanzarla desde el servidor (la URL ya trae host/usuario/clave).

## 2. Crear la llave SSH de deploy

```bash
# En TU máquina local
ssh-keygen -t ed25519 -f ~/.ssh/orderfox_deploy -C "github-actions-deploy" -N ""

# Instalar la pública en el servidor (pide tu password SSH normal)
ssh-copy-id -i ~/.ssh/orderfox_deploy.pub ubuntu@TU_IP
```

## 3. Agregar los secrets en GitHub

Repo → **Settings → Secrets and variables → Actions** → New repository secret:

| Secret | Valor |
|--------|-------|
| `SSH_PRIVATE_KEY` | Contenido de `~/.ssh/orderfox_deploy` (la llave **privada**, texto completo) |
| `SSH_HOST` | IP pública o dominio del servidor Oracle Cloud |
| `SSH_USER` | *(opcional)* usuario SSH — por defecto `ubuntu` |
| `SSH_PORT` | *(opcional)* puerto SSH — por defecto `22` |

> El job `deploy` se define con `environment: production`, así que también puedes
> guardar los secrets a nivel de environment (Settings → Environments → production)
> si quieres aprobación manual antes de desplegar (protection rules).

## 4. Probar

1. Haz push a `main`.
2. En GitHub → Actions → workflow **CI**: verás los jobs `test`, `lint` y luego `deploy`.
3. Cuando `deploy` termine ✅:
   ```bash
   ssh ubuntu@TU_IP
   tail -30 /var/log/orderfox/deploy.log        # registro del deploy
   systemctl status orderfox                     # servicio activo
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/   # 200/302
   ```

## 5. Si algo falla

- **El job `deploy` falla pero tests/lint pasaron**: revisa la salida del job en
  GitHub Actions (muestra el log del script) y el `deploy.log` en el servidor.
- **`git pull` falló**: el servidor tiene cambios locales sin commitear
  (`git -C /var/www/orderfox status` para verlos).
- **Health check falló**: `sudo journalctl -u orderfox -n 50` para ver el error.
- **Rollback**: `git revert` + push revierte el código automáticamente. Para la BD,
  restaurar un backup de `/var/log/orderfox/backups/` o `flask db downgrade` manual.

## Notas

- El Astro (menú público) es un despliegue aparte (`astro/`) — este flujo solo
  actualiza la app Flask.
- La primera vez que el job corre, el `StrictHostKeyChecking=accept-new` acepta la
  huella del servidor automáticamente.
- Si quieres mayor seguridad, puedes restringir la llave `orderfox_deploy` a solo
  ejecutar el script de deploy usando `command=` en `authorized_keys` del servidor.