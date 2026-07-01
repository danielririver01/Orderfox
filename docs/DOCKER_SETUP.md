# Docker Setup — Orderfox + Receipt Scanner

## ⚠️ Estructura del proyecto

```
C:\Users\danie\Desktop\
├── Orderfox\                  # Flask (Python) — backend principal
│   ├── Dockerfile             # Producción
│   ├── Dockerfile.dev         # Desarrollo (hot reload)
│   ├── docker-compose.yml     # Orquestación (todos los servicios)
│   └── docker-compose.override.yml  # Overrides para dev
│
└── Receipt-Scanner-AI\        # Next.js (Node) — escáner de recibos
    ├── Dockerfile             # Producción (multi-stage, alpine)
    └── Dockerfile.dev         # Desarrollo (bookworm-slim, SWC fix)
```

**docker-compose.yml** vive en `Orderfox/` y orquesta ambos proyectos más la base de datos.

---

## Prerrequisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows)
- WSL2 con kernel actualizado (para rendimiento)
- Puertos libres: `3306` (MySQL), `5000` (Flask), `3000` (Next.js)

---

## Primera vez / setup inicial

```bash
# 1. Clonar ambos repositorios en C:\Users\danie\Desktop\
git clone <orderfox-repo> Orderfox
git clone <scanner-repo> Receipt-Scanner-AI

# 2. Crear archivos .env (uno en cada proyecto)
#    Orderfox/.env    → variables Flask, DB, Clerk, Mercado Pago, etc.
#    Receipt-Scanner-AI/.env → variables Clerk, DeepSeek, Cloudinary, etc.

# 3. Construir y arrancar todo (modo desarrollo)
cd Orderfox
docker compose up -d --build

# 4. Verificar que todos los contenedores estén running
docker ps
```

---

## Comandos esenciales

### Modo desarrollo (usa `docker-compose.override.yml`)

```bash
# Arrancar todos los servicios
docker compose up -d

# Arrancar solo un servicio específico
docker compose up -d orderfox
docker compose up -d receipt-scanner

# Reconstruir un servicio (tras cambios en Dockerfile o dependencias)
docker compose up -d --build <servicio>

# Ver logs de un servicio
docker compose logs -f receipt-scanner

# Detener todo
docker compose down

# Detener todo + eliminar volúmenes (borra la BD)
docker compose down -v
```

### Modo producción (usa `docker-compose.yml` directamente)

```bash
# Forzar override vacío para usar solo el compose base
docker compose -f docker-compose.yml up -d --build
```

---

## Servicios

| Servicio | Container name (dev) | Container name (prod) | Puerto | Depende de |
|---|---|---|---|---|
| **mysql** | `orderfox-db` | `orderfox-db` | `3306` | — |
| **orderfox** | `orderfox-app-dev` | `orderfox-app` | `5000:5000` | mysql (healthy) |
| **orderfox-scheduler** | `orderfox-scheduler-dev` | `orderfox-scheduler` | — | mysql (healthy) |
| **receipt-scanner** | `receipt-scanner-dev` | `receipt-scanner` | `3000:3000` | mysql (healthy) |

### Red

Todos los servicios comparten la red `orderfox-net` (bridge). Se comunican por nombre de contenedor:
- `http://orderfox:5000` → desde el scanner hacia Orderfox
- `http://receipt-scanner:3000` → desde Orderfox hacia el scanner

---

## Volúmenes persistentes

- `mysql-data` → datos de MariaDB (no borrar sin cuidado)
- `/app/node_modules` (anónimo, solo dev) → preserva `node_modules` dentro del contenedor del scanner
- `/app/.next` (anónimo, solo dev) → preserva caché de Next.js

Si un build nuevo no se refleja, puede ser un volumen anónimo viejo:

```bash
# Limpiar volúmenes anónimos no usados
docker volume prune

# O forzar recreación completa
docker compose down -v
docker compose up -d --build
```

---

## Problemas comunes

### 1. "Failed to load SWC binary for linux/x64" (Receipt-Scanner-AI)

Next.js 15 en Linux necesita `@next/swc-linux-x64-gnu`. El `Dockerfile.dev` ya lo incluye:

```dockerfile
RUN pnpm add -w @next/swc-linux-x64-gnu@15.5.18
```

Si persiste tras un rebuild, eliminar el volumen anónimo de `node_modules`:

```bash
docker compose down receipt-scanner
docker volume prune
docker compose up -d --build receipt-scanner
```

### 2. MySQL connection refused

Esperar a que `orderfox-db` pase el healthcheck. Revisar con:

```bash
docker inspect orderfox-db --format='{{.State.Health.Status}}'
```

Si nunca se pone healthy, revisar que `MYSQL_ROOT_PASSWORD` coincida en `.env`.

### 3. "packages field missing or empty" (pnpm)

El archivo `pnpm-workspace.yaml` en Receipt-Scanner-AI debe tener:

```yaml
packages:
  - '.'
```

Sin este campo, pnpm v9 no reconoce el proyecto como workspace.

### 4. Hot reload no funciona

En desarrollo se usa bind mount (`volumes:` en override). Verificar que:
- El archivo que modificaste está dentro del directorio montado
- Flask recarga automáticamente con `FLASK_DEBUG=True`
- Next.js recarga solo; si no, reiniciar el contenedor

```bash
docker compose restart receipt-scanner
```

### 5. CSS no se actualiza (Orderfox)

Tailwind CSS requiere build separado. En desarrollo:

```bash
# En la máquina host (no dentro del contenedor)
cd Orderfox
npm run watch:css
```

O forzar rebuild del CSS dentro del contenedor:

```bash
docker exec orderfox-app-dev npm run build:css
```

---

## URLs en desarrollo

| Servicio | URL |
|---|---|
| Orderfox (Flask) | `http://localhost:5000` |
| Receipt Scanner (Next.js) | `http://localhost:3000` |
| Base de datos (MariaDB) | `localhost:3306` (usuario `root`, pass `root` por defecto) |

---

## Notas sobre el `Dockerfile.dev` del scanner

El `Dockerfile.dev` usa `node:22-bookworm-slim` (Debian, no Alpine) porque:
- `@next/swc-linux-x64-gnu` necesita glibc (Alpine usa musl)
- `canvas` y `sharp` necesitan compilar native addons

Orden de capas importante:

```dockerfile
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --no-frozen-lockfile
RUN pnpm add -w @next/swc-linux-x64-gnu@15.5.18   # ← SWC para linux
COPY . .                                            # ← código fuente al final
```

No se puede mover `pnpm add` después de `COPY . .` porque `pnpm-workspace.yaml` del host entraría antes de tener los packages registrados.

---

## Respaldo / restore de BD

```bash
# Respaldar
docker exec orderfox-db mariadb-dump -u root -proot orderfox > backup.sql

# Restaurar
docker exec -i orderfox-db mariadb -u root -proot orderfox < backup.sql
```
