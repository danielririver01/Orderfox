# ARCH-03: Política de Autenticación

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

> Documento canónico — la fuente de verdad para el flujo de autenticación del proyecto.

---

## 1. Filosofía: La Base de Datos es la Fuente de Verdad

El sistema **nunca** otorga acceso sin un registro correspondiente en la base de datos local.
Clerk es el proveedor de identidad OAuth, pero la base de datos es el sistema de registro autoritativo.

**Regla fundamental:** Si un usuario existe en Clerk pero NO en la BD local → se rechaza el acceso con error `USER_NOT_REGISTERED`, a menos que sea un flujo de registro que auto-crea el usuario con plan trial.

---

## 2. Flujo de Autenticación por Tipo de Cliente

### 2.1 Clerk OAuth (Web — Dashboard)

```
1. Usuario hace clic en "Iniciar sesión con Clerk"
2. Clerk muestra su UI de login/registro
3. Clerk redirige a /auth/clerk-callback con código de autorización
4. Servidor intercambia código por token Clerk
5. Servidor obtiene perfil del usuario (clerk_id, email, username)
6. Busca User.clerk_id en BD local:
   ├── Existe → inicia sesión Flask, redirige a /dashboard/index
   └── NO existe → flujo de auto-creación:
       ├── Crea User con clerk_id, email, username
       ├── Redirige a /auth/setup-account
       ├── Usuario crea restaurante
       ├── Asigna trial (7 días) + 100 tokens AI
       └── Redirige a /dashboard/index
```

### 2.2 JWT (API Móvil / Scanner IA)

```
1. Cliente envía Authorization: Bearer <jwt_token>
2. Servidor valida firma JWT contra Clerk (JWKS endpoint)
3. Extrae clerk_id del payload del JWT
4. Busca User.clerk_id en BD local:
   ├── Existe → otorga acceso (request.user = usuario)
   └── NO existe → responde 401:
       {"success": false, "error_code": "USER_NOT_REGISTERED"}
```

**JWT para Scanner IA:**
- Clerk genera JWT firmado con `CLERK_SECRET_KEY`
- Servidor valida en cada request
- 24 horas de expiración (configurable en `JWT_ACCESS_TOKEN_EXPIRES`)

### 2.3 Sesión Tradicional (Email + Password)

```
1. Usuario POST /auth/login con email + password
2. Servidor busca User.email en BD:
   ├── Existe → verifica password hash
   │   ├── Correcto → inicia sesión Flask
   │   └── Incorrecto → error 401 INVALID_CREDENTIALS
   └── NO existe → error 401 INVALID_CREDENTIALS
3. Sesión almacenada en cookie segura (no permanente)
```

---

## 3. Auto-Creación de Usuarios (Flujo Trial)

**Disparador:** Usuario autenticado en Clerk que NO existe en BD local.

```
1. Recibir de Clerk: clerk_id, email, username
2. Validar elegibilidad de trial:
   - Verificar TrialHistory (email + whatsapp únicos)
   - Si ya usó trial → redirigir a login con mensaje
3. Crear User:
   INSERT INTO users (clerk_id, email, username, restaurant_id=null)
4. Usuario redirigido a /auth/setup-account (formulario)
5. Usuario completa:
   - Nombre del restaurante
   - Slug (validado contra RESERVED_SLUGS)
   - Whatsapp
6. Sistema crea:
   - Restaurant: slug, name, whatsapp, plan_type='emprendedor',
     subscription_expires_at=now+7d, is_active=True, has_used_trial=True
   - Actualiza User.restaurant_id
   - Crea TrialHistory (email + whatsapp)
   - Crea AITokenWallet: plan_limit=100, plan_tokens=100, extra_tokens=0
7. Redirige a /dashboard/index
```

### Reglas del Trial

| Aspecto | Valor |
|---------|-------|
| Duración | 7 días (hard-coded) |
| Grace period | 14 días después de expiración |
| Plan asignado | Emprendedor |
| Límite de productos | Ilimitado (durante trial) |
| Tokens AI | 100 |
| Restricción | Un trial por email + whatsapp |
| Control | Tabla TrialHistory |

---

## 4. Decoradores de Autenticación

Definidos en `app/utils/jwt_auth.py`:

| Decorador | Rutas | Verifica |
|-----------|-------|----------|
| `@login_required` | Web | user_id en sesión Flask |
| `@jwt_login_required` | API | JWT válido firmado por Clerk |
| `@active_required` | Web | Sesión + suscripción activa (no expired/grace) |
| `@jwt_active_required` | API | JWT + suscripción activa |
| `@flexible_login_required` | Web/API | Sesión O JWT (cualquier autenticación) |
| `@flexible_active_required` | Web/API | Cualquier auth + suscripción activa |
| `@feature_required(nombre)` | Web | Sesión + feature habilitada en el plan |

**Uso típico:**
- Páginas del dashboard: `@login_required`
- CRUD de productos: `@active_required`
- API de Scanner IA: `@jwt_active_required`
- Webhooks de Mercado Pago: sin decorador (CSRF exento)

---

## 5. Estados de Suscripción y Acceso

| Estado | Descripción | CRUD | API | Dashboard |
|--------|-------------|------|-----|-----------|
| `active` | Suscripción vigente | ✅ | ✅ | ✅ |
| `trial` | Período de prueba (7d) | ✅ | ✅ | ✅ |
| `grace_period` | 14 días post-expiración | ❌ | ❌ | ✅ (solo lectura) |
| `expired` | Sin suscripción activa | ❌ | ❌ | ⚠️ (limitado) |
| `inactive` | Cuenta desactivada | ❌ | ❌ | ❌ (solo login) |

El bloqueo de CRUD en grace_period se implementa en `app/__init__.py` via `before_request`:
```python
@app.before_request
def block_grace_period_crud():
    if request.endpoint and not request.path.startswith('/api/'):
        # Verifica suscripción y bloquea POST/PUT/DELETE si está en grace_period
```

---

## 6. Códigos de Error

| Código | Significado | HTTP | Causa Típica |
|--------|-------------|------|--------------|
| `USER_NOT_REGISTERED` | Usuario en Clerk pero sin BD local | 401 | JWT de usuario no registrado |
| `SUBSCRIPTION_EXPIRED` | Suscripción vencida | 403 | Grace period terminado |
| `GRACE_PERIOD` | En período de gracia | 403 | Intento de CRUD en grace period |
| `FEATURE_NOT_AVAILABLE` | Plan no incluye funcionalidad | 403 | Ej: modifiers en plan Emprendedor |
| `TOKEN_INSUFFICIENT` | Sin tokens AI disponibles | 402 | plan_tokens + extra_tokens = 0 |
| `INVALID_CREDENTIALS` | Email o contraseña incorrectos | 401 | Login tradicional fallido |
| `TRIAL_ALREADY_USED` | Email/whatsapp ya usó trial | 409 | Segundo intento de trial |

---

## 7. Integración con Scanner IA

Scanner IA usa JWT de Clerk para autenticación server-to-server:

1. Scanner IA genera JWT usando `CLERK_SECRET_KEY`
2. Envía `Authorization: Bearer <jwt>` en cada request
3. Servidor valida JWT → extrae `clerk_id` → busca User
4. Si el usuario tiene `AITokenWallet.can_scan()` → permite la operación
5. Consume token: registra `AITokenTransaction(type='consume', source='scanner_ia')`

**Alternativa:** Servicio a servicio via `SERVICE_API_KEY` (header `x-api-key`):
- Bypass completo de rate limiting y autenticación de usuario
- Usado para operaciones internas del sistema

---

## 8. Seguridad

- Contraseñas hasheadas con Werkzeug (`generate_password_hash`)
- Sesiones Flask con cookie segura (HttpOnly, SameSite)
- JWT firmado por Clerk (no generación local de tokens)
- CSRF: API exenta, web protegido por Flask-WTF
- Rate limiting en pedidos: prevención de abuso

---

## 9. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
