# Política de Autenticación

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Filosofía: La Base de Datos es la Fuente de Verdad

El sistema **nunca** otorga acceso sin un registro correspondiente en la base de datos local. Clerk es el proveedor de identidad OAuth, pero la base de datos es el sistema de registro autoritativo.

---

## 2. Flujo de Autenticación

### 2.1 Clerk OAuth (Web)
1. Usuario inicia sesión via Clerk (redirect)
2. Clerk callback recibe `clerk_id` + datos del perfil
3. Sistema busca `User.clerk_id` en la BD local
   - **Si existe** → inicia sesión, redirige al dashboard
   - **Si NO existe** → auto-crea el usuario con plan trial

### 2.2 JWT (API Móvil/Externa)
1. Cliente envía `Authorization: Bearer <token>` (JWT firmado por Clerk)
2. Sistema valida la firma del JWT contra Clerk
3. Extrae `clerk_id` del payload del JWT
4. Busca `User.clerk_id` en la BD local
   - **Si existe** → otorga acceso
   - **Si NO existe** → rechaza con error `USER_NOT_REGISTERED`

### 2.3 Sesión (Dashboard Web)
- Flask session manejada por cookies seguras
- `login_required` decorator verifica `user_id` en sesión
- Sesión expira al cerrar navegador (no permanente)

---

## 3. Auto-Creación de Usuarios (Trial)

Cuando un usuario de Clerk no existe en la BD local:

```
1. Recibir clerk_id, email, username de Clerk
2. Crear registro en tabla `users`
   - clerk_id, email, username
   - restaurant_id = NULL (aún sin restaurante)
3. Redirigir a /auth/setup-account
4. Usuario completa formulario de registro de restaurante
5. Sistema crea Restaurant + asocia User
6. Asigna plan trial (7 días) + 100 tokens AI
   - is_active = true, plan_type = 'emprendedor'
   - subscription_expires_at = now + 7 days
   - Registro en TrialHistory (email + whatsapp)
```

### Reglas del Trial
- **Duración:** 7 días (hard-coded, no configurable)
- **Grace period:** 14 días después de expiración (solo lectura)
- **Restricción:** un trial por email + whatsapp (TrialHistory)
- **Tokens:** 100 tokens AI de cortesía al crear el restaurante

---

## 4. Estados Posibles

| Estado | Descripción | Acceso |
|--------|-------------|--------|
| `active` | Suscripción vigente | Lectura + escritura |
| `trial` | Período de prueba (7 días) | Lectura + escritura |
| `grace_period` | 14 días post-expiración | Solo lectura |
| `expired` | Sin suscripción activa | Solo dashboard (sin CRUD) |
| `inactive` | Cuenta desactivada manualmente | Solo login |

---

## 5. Códigos de Error

| Código | Significado | HTTP Status |
|--------|-------------|-------------|
| `USER_NOT_REGISTERED` | Usuario autenticado en Clerk pero sin registro local | 401 |
| `SUBSCRIPTION_EXPIRED` | Suscripción vencida sin período de gracia | 403 |
| `GRACE_PERIOD` | Suscripción en período de gracia (solo lectura) | 403 |
| `FEATURE_NOT_AVAILABLE` | El plan no incluye esta funcionalidad | 403 |
| `TOKEN_INSUFFICIENT` | No hay suficientes tokens AI | 402 |
| `INVALID_CREDENTIALS` | Email o contraseña incorrectos | 401 |

---

## 6. Decoradores

| Decorator | Ruta | Verifica |
|-----------|------|----------|
| `@login_required` | Web | Sesión activa |
| `@jwt_login_required` | API | JWT válido |
| `@active_required` | Web | Sesión + suscripción activa |
| `@jwt_active_required` | API | JWT + suscripción activa |
| `@flexible_login_required` | Web/API | Sesión o JWT |
| `@flexible_active_required` | Web/API | Sesión o JWT + suscripción activa |
| `@feature_required('feature_name')` | Web | Sesión + feature habilitada |

---

## 7. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
