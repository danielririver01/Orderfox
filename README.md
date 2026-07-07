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
- **Planes flexibles** — Desde $30.000 COP/mes. Prueba gratuita de 10 días sin tarjeta de crédito.

## Tecnología

- **Backend:** Python (Flask), SQLAlchemy, MySQL
- **Frontend:** Tailwind CSS, JavaScript vanilla, Jinja2
- **Infraestructura:** Docker, Gunicorn
- **Servicios externos:** Clerk (autenticación), Mercado Pago (pagos), Cloudinary (imágenes), ntfy.sh (notificaciones)

## Inicio rápido

```bash
# Clonar el repositorio
git clone https://github.com/danielririver01/Orderfox.git
cd Orderfox

# Copiar y configurar variables de entorno
cp .env.example .env

# Iniciar con Docker
docker compose up -d
```

La aplicación estará disponible en `http://localhost:5000`.

## Licencia

Uso privado. Todos los derechos reservados.
