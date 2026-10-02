# Orderfox / Velzia

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-black)](https://flask.palletsprojects.com)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4.2.4-38bdf8)](https://tailwindcss.com)

Plataforma SaaS de gestión de pedidos para restaurantes colombianos. Crea tu menú digital, recibe pedidos por código QR, gestiona tu restaurante desde un panel de control y automatiza tus finanzas con escáner de facturas por IA.

## Funcionalidades principales

- **Menú digital** — Crea y actualiza tu menú en tiempo real. Sin imprimir.
- **Pedidos por QR** — Cada mesa tiene su propio código QR. El cliente escanea, elige y pide.
- **Panel de control** — Administra productos, categorías, pedidos y mesas desde un solo lugar.
- **Notificaciones en tiempo real** — Cuando llega un pedido, el dueño recibe una notificación al instante.
- **Pagos en línea** — Integración con Mercado Pago (la pasarela de pagos más usada en Colombia).
- **Escáner de facturas con IA** — Toma fotos de tus facturas y el sistema las clasifica automáticamente.
- **Planes flexibles** — Desde $30.000 COP/mes. Prueba gratuita de 60 días sin tarjeta de crédito.

## Tecnología

- **Backend:** Python (Flask), SQLAlchemy, PostgreSQL
- **Frontend:** Tailwind CSS, JavaScript vanilla, Jinja2
- **Infraestructura:** Docker, Gunicorn
- **Servicios externos:** Clerk (autenticación), Mercado Pago (pagos), Cloudinary (imágenes), ntfy.sh (notificaciones)

## Inicio rápido

> **Producción (Oracle Cloud):** systemd + gunicorn con `-c gunicorn_config.py`
> tras nginx. El despliegue automático y su verificación de salud están en
> `deploy/AUTO_DEPLOY.md`. Docker es solo para desarrollo local.

### Con Docker (desarrollo local)

`docker compose up -d` levanta la app (`:5000`), el scheduler y **Redis** (el
storage compartido del rate limiter — solo escucha en `127.0.0.1:6379`).
Requisitos:

1. **Base de datos propia** — el compose no incluye ninguna: apunta
   `DATABASE_URL` en `.env` a tu PostgreSQL (desde el contenedor usa
   `host.docker.internal` en vez de `localhost`).
2. **Variables de entorno** — `cp .env.example .env` y configúralas.

```bash
git clone https://github.com/danielririver01/Orderfox.git
cd Orderfox
cp .env.example .env        # configura DATABASE_URL y demás
docker compose up -d        # app + scheduler + redis
curl http://localhost:5000/health   # 200 = app viva, BD y Redis conectados
```

¿Solo trabajas con `python run.py` (Flask fuera de Docker)? Levanta únicamente
Redis y la app lo usará vía `RATELIMIT_STORAGE_URL`:

```bash
docker compose up -d redis
python run.py
```

El servicio `receipt-scanner` requiere el repo hermano privado
`../Receipt-Scanner-AI` y vive tras un profile para no romper el arranque
en un clon limpio:

```bash
docker compose --profile scanner up -d
```

### Sin Docker

Ver `AGENTS.md` → Quick Start (venv, `flask db upgrade`, `npm run build:css`,
`python run.py`).

## Licencia

Uso privado. Todos los derechos reservados.
