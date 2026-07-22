# Better Stack Error Tracking — Guía de Integración

## ¿Qué es?

[Better Stack Error Tracking](https://betterstack.com/error-tracking) es un servicio de monitoreo
de errores (competencia de Sentry) que captura excepciones, stack traces y errores HTTP para
diagnosticar problemas en producción.

**Cómo funciona:**
Better Stack **soporta el protocolo de Sentry**. Esto significa que reutilizamos
`sentry-sdk` apuntando el DSN al endpoint de Better Stack, sin instalar dependencias
adicionales.

## Configuración

### 1. Obtener DSN

1. Ir a [Better Stack → Error Tracking](https://logs.betterstack.com/error-tracking)
2. Crear un nuevo proyecto (Sentry-compatible)
3. Copiar el DSN (empieza con `https://...@ingest.betterstack.com/...`)

### 2. Variable de entorno

```env
# .env
SENTRY_DSN=https://xxx@ingest.betterstack.com/yyy
```

### 3. Verificar inicialización

Revisar los logs del servidor al iniciar:

```
Better Stack Error Tracking initialized
```

Si no hay DSN configurado, el SDK no se inicia y no hay overhead.

## Qué se captura automáticamente

| Tipo | Cómo |
|------|------|
| Excepciones HTTP 500 | FlaskIntegration |
| Errores en Blueprints | FlaskIntegration |
| Excepciones en DB | SqlalchemyIntegration |
| `app.logger.error(...)` | LoggingIntegration (event_level=ERROR) |
| `app.logger.warning(...)` | LoggingIntegration (breadcrumb level=INFO) |
| Tareas APScheduler | Se capturan vía excepción no controlada |
| Copilot VZ / Scanner IA | Ya usan `app.logger`, atrapados por LoggingIntegration |

## Contexto automático en cada error

Cada error incluye tags para identificar rápidamente el origen:

- **`restaurant_id`** — restaurante afectado (solo si hay sesión activa)
- **`user_id` + `email`** — usuario logueado (solo si hay JWT válido)
- **`app_version`** — versión de Velzia (`APP_VERSION`)
- **`module`** — primer segmento de la URL (ej: `api`, `insights`, `auth`, `menu`)

## Información protegida (nunca se envía)

La función `before_send` sanitiza:

**Headers HTTP:**
- `Authorization` (Bearer tokens)
- `Cookie`, `Set-Cookie`
- `X-API-Key`, `X-Auth-Token`, `Proxy-Authorization`

**Cuerpo de la request:**
- `password`, `token`, `secret`, `api_key`
- `access_token`, `refresh_token`, `jwt`, `cookie`, `session`

Si el cuerpo no es JSON válido pero contiene palabras sensibles, se enmascara completo.

## Buenas prácticas

### Usar `app.logger.error()` en lugar de `print()`

Los `logger.error()` se envían automáticamente a Better Stack:

```python
app.logger.error("Pago rechazado", extra={'mp_status': status})
```

### Agregar contexto adicional en operaciones críticas

```python
with sentry_sdk.push_scope() as scope:
    scope.set_tag('order_id', order.id)
    scope.set_extra('total', order.total)
    realizar_pago(order)
```

### Excluir errores esperados

Si hay endpoints que deliberadamente retornan 500 en ciertas condiciones,
pueden ignorarse en el panel de Better Stack (no en el código).

## Límites y consideraciones

### APScheduler

Las tareas programadas NO llevan contexto de `restaurant_id` o `user_id`
porque se ejecutan fuera del ciclo de una request HTTP. Se identifican
por el tag `module=root`.

### Development

En desarrollo no hay DSN configurado → el SDK no se inicia.
El comportamiento de Flask no se modifica.

### Performance

`traces_sample_rate=0` — no se envían trazas de performance,
solo errores. El overhead es mínimo (~1ms en caso de error).

## Troubleshooting

### Errores no aparecen en Better Stack

1. Verificar `SENTRY_DSN` en `.env`
2. Verificar logs de inicio: "Better Stack Error Tracking initialized"
3. Forzar un error de prueba: agregar `1/0` en una ruta y llamarla
4. Revisar filtros en el panel de Better Stack

### Errores con datos sensibles visibles

Revisar la función `strip_sensitive_data` en `app/__init__.py` y agregar
el campo faltante a `SENSITIVE_BODY_KEYS` o `SENSITIVE_HEADERS`.

### En desarrollo quiero probar errores

Configurar un DSN de prueba (Better Stack ofrece un plan gratuito)
o usar un proyecto de prueba en Better Stack.

## Archivos involucrados

| Archivo | Propósito |
|---------|-----------|
| `app/__init__.py:43-113` | Inicialización + sanitización + contexto |
| `settings.py:77` | Config `SENTRY_DSN` desde `env` |
| `.env.example:40` | Documentación de la variable |
| `requirements-dev.txt` | `sentry-sdk==2.28.0` (ya incluido) |
