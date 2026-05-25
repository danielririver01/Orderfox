# Política de Autenticación - Base de Datos como Única Verdad

## Cambios Importantes (25-Mayo-2026)

### Regla Crítica: La base de datos es la única verdad

**ANTES:** Cuando un usuario autenticado en Clerk pero no existía en BD, se creaba automáticamente con plan NONE, quebrando el flujo de la aplicación.

**AHORA:** 
- Si usuario está en Clerk pero NO en BD: **RECHAZAMOS acceso**
- Se cierra la sesión de Clerk automáticamente
- Se muestra mensaje: "Debe registrarse en la plataforma para poder acceder."
- Error code: `USER_NOT_REGISTERED`

### Archivos Modificados
1. `/app/routes/auth.py` - Endpoint `/api/sync-clerk`
   - Rechaza usuarios no registrados en BD (antes los creaba)
   - Devuelve 401 con error_code USER_NOT_REGISTERED

2. `/app/template/auth/index.html`
   - Maneja error_code USER_NOT_REGISTERED
   - Cierra sesión Clerk automáticamente
   - Muestra UI clara indicando que debe registrarse

3. `/app/template/auth/sync_clerk.html`
   - Similar manejo del error USER_NOT_REGISTERED
   - Cierra sesión y muestra mensaje

### Nunca Crear Usuarios Implícitamente
- No crear usuarios solo porque tienen sesión en Clerk
- No asignar planes por defecto
- Validar siempre en BD antes de permitir acceso