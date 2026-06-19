# ARCH-01: Visión General de Arquitectura

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                    Navegador Web                         │
│  (Dashboard Reactivo · Menú Público · Auth Clerk)       │
└──────────────┬──────────────────────────────┬───────────┘
               │  Session Cookie              │  Clerk OAuth
               ▼                              ▼
┌──────────────────────────────┬──────────────────────────┐
│   Flask Web Blueprints       │   Clerk OAuth Proxy      │
│   (HTML + Jinja2)           │   (/auth/*)              │
├──────────────────────────────┼──────────────────────────┤
│   Flask API Blueprints       │   JWT Auth               │
│   (JSON REST)                │   (API Móvil/Scanner)    │
├──────────────────────────────┴──────────────────────────┤
│               Service Layer (app/services/)              │
│   Auth · Order · Product · Category · Table · Token     │
├─────────────────────────────────────────────────────────┤
│               Utils (app/utils/)                         │
│   Subscription · Rate Limiter · JWT Auth · Image Handler│
├─────────────────────────────────────────────────────────┤
│               Flask Extensions                           │
│   SQLAlchemy · Mail · Limiter · APScheduler · CORS      │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    MySQL 8.x                             │
│   restaurants · users · categories · products · orders  │
│   modifiers · tables · ai_token_wallets · etc.          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│               Servicios Externos                        │
│   Clerk (OAuth/JWT) · Cloudinary · Mercado Pago         │
│   Scanner IA · Gmail SMTP                               │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Patrón Arquitectónico

**Monolito Full-Stack** — Un solo servidor Flask sirve tanto las páginas HTML del dashboard como las APIs JSON para clientes externos.

### Principios de Diseño

1. **Doble Blueprint**: Cada dominio tiene un blueprint web (`/products`) y uno API (`/api/products`)
2. **Capa de Servicios**: La lógica de negocio vive en `app/services/`, no en las rutas
3. **Estado en Backend**: Todo cálculo de estado (suscripción, permisos) se hace en el servidor
4. **UTC como fuente única de verdad**: Sin excepciones
5. **Base de datos como sistema de registro**: Clerk es el proveedor de identidad, pero la BD es la autoridad

---

## 3. Flujo de Solicitudes

### Web (Dashboard)
```
1. Usuario → /dashboard/products
2. Flask session auth (cookie)
3. before_request: verifica suscripción activa
4. Route handler → Service method → SQLAlchemy query
5. Template render (Jinja2) → HTML response
```

### API (Móvil/Scanner IA)
```
1. Cliente → /api/orders/create
2. JWT auth (Authorization header)
3. before_request: verifica suscripción activa (si aplica)
4. Route handler → Service method → SQLAlchemy query
5. JSON response {"success": true, "data": {...}}
```

---

## 4. Componentes Clave

### App Factory (`app/__init__.py`)
El punto de entrada `create_app()`:
1. Crea instancia Flask con carpetas personalizadas
2. Carga configuración desde `settings.Config`
3. Inicializa extensiones: SQLAlchemy, Migrate, Mail, Limiter, JWT, CSRF, CORS, APScheduler
4. Configura ProxyFix para reverse proxy
5. Configura WhiteNoise para archivos estáticos (producción)
6. Registra los 17 blueprints
7. Instala hooks `before_request`:
   - Exime rutas `/api/*` de CSRF
   - Bloquea operaciones CRUD durante período de gracia
8. Inyecta variables globales en templates (usuario, suscripción)
9. Registra comandos CLI y manejadores de error (403, 404, 500)

### Servicios
Cada servicio usa el patrón:
```python
@staticmethod
def metodo(param):
    # éxito → retorna (resultado, None)
    # error → retorna (None, {"error": "mensaje"})
    return (resultado, None)
```

### Decoradores de Autenticación
Jerarquía en `app/utils/jwt_auth.py`:
- `@login_required` → verifica sesión
- `@active_required` → sesión + suscripción activa
- `@jwt_login_required` → JWT válido
- `@jwt_active_required` → JWT + suscripción activa
- `@flexible_login_required` y `@flexible_active_required` → aceptan ambos

---

## 5. Estrategia de CSRF

| Tipo de Ruta | CSRF | Mecanismo |
|-------------|------|-----------|
| Web (`/dashboard/*`) | Habilitado | `{{ csrf_token() }}` en formularios |
| API (`/api/*`) | Exento | `before_request` setea `request._csrf_exempt = True` |
| Webhooks | Exento | `@csrf.exempt` decorator |

---

## 6. Tolerancia a Fallos

- **Rate Limiter**: In-memory (se reinicia al reiniciar el servidor)
- **APScheduler**: Jobs críticos (expiración de pedidos, limpieza de cuentas)
- **Image Upload**: Subida a Cloudinary + caché local en `app/static/uploads/`
- **Conexión DB**: Pool con `pool_pre_ping=True` para detectar conexiones muertas

---

## 7. Limitaciones Conocidas

- Rate limiter en memoria → no escala horizontalmente (considerar Redis)
- Archivos subidos no se limpian automáticamente del caché local
- Sin sistema de colas para tareas asíncronas (APScheduler es básico)

---

## 8. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
