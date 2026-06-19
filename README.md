# Orderfox — SaaS de Gestión de Pedidos para Restaurantes

[![License: ISC](https://img.shields.io/badge/License-ISC-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-black)](https://flask.palletsprojects.com)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4.2.4-38bdf8)](https://tailwindcss.com)

Plataforma SaaS para que restaurantes gestionen pedidos digitales, menús QR, y operaciones del negocio — todo desde un dashboard centralizado.

---

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| **Backend** | Flask 3.x (Python) |
| **Base de datos** | MySQL 8.x + SQLAlchemy ORM |
| **Frontend** | Vanilla JS + Tailwind CSS 4 |
| **Autenticación** | Clerk OAuth + JWT |
| **Pagos** | Mercado Pago |
| **Imágenes** | Cloudinary CDN |
| **PWA** | Workbox + Dexie (IndexedDB) |

---

## Inicio Rápido

```bash
# 1. Clonar el repositorio
git clone https://github.com/danielririver01/Orderfox.git
cd Orderfox

# 2. Activar entorno virtual (Windows)
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt
npm install

# 4. Configurar variables de entorno
cp .env.example .env   # Crear desde plantilla

# 5. Inicializar base de datos
flask db upgrade

# 6. Iniciar servidor de desarrollo
python run.py
```

Abrir [http://localhost:5000](http://localhost:5000).

---

## Documentación

Toda la documentación del proyecto está en [`docs/`](docs/README.md):

| Categoría | Documentos |
|-----------|-----------|
| **Arquitectura** | Visión general, diagrama ERD, autenticación, suscripciones |
| **Guías técnicas** | Timezone, rate limiting, API reference, integraciones |
| **Procedimientos** | Deployment, respuesta a incidentes, onboarding, testing |
| **Gobernanza** | Código de conducta, políticas de seguridad y contribución |

---

## Licencia

Distribuido bajo licencia ISC. Ver [`LICENSE`](LICENSE) para más información.
