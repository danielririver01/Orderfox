# Manejo de Tiempos y Suscripciones (UTC)

## Filosofía: Fuente Única de Verdad

Para evitar inconsistencias entre el servidor, la base de datos y el navegador del usuario, el sistema ha sido sanitizado para usar **UTC** como única referencia temporal.

### Reglas de Oro

1. **Almacenamiento**: Todas las fechas en la base de datos (MySQL) se almacenan en UTC.
2. **Cálculos**: TODO cálculo de expiración o estado se realiza exclusivamente en el backend (`app/utils/subscription.py`).
3. **Comparación**: Siempre se usa `datetime.now(timezone.utc)` para comparar con las fechas de la base de datos.
4. **Presentación**: El frontend NO calcula días restantes. Recibe un objeto de estado ya procesado.

---

## Implementación Técnica

### 1. Backend Utility (`app/utils/subscription.py`)

La función central es `get_subscription_status(restaurant)`.

**Retorna un diccionario completo:**

- `is_active`: Booleano (acceso al sistema).
- `status`: String identificador (`active`, `expiring_soon`, `grace_period`, `expired`, `inactive`).
- `message`: Mensaje legible en español para el usuario.
- `formatted_expiration`: Fecha formateada (ej: "15 de marzo de 2026").
- `badge_class`: Clases CSS de Tailwind para el badge.
- `badge_text`: Texto para el badge.
- `can_crud`: Booleano para permisos de escritura.

### 2. Dashboard (`app/routes/dashboard.py`)

La ruta `/subscription` ha sido simplificada. Su único trabajo es obtener el objeto de estado y pasarlo al template.

### 3. Frontend (`app/template/dashboard/subscription.html`)

El template se ha limpiado de lógica compleja. Ahora consume directamente los campos de `sub_status`:

```html
<div class="{{ sub_status.badge_class }}">{{ sub_status.message }}</div>
```

---

## Verificación

Para asegurar que cualquier cambio futuro mantenga esta integridad, existe una suite de pruebas:

```bash
.venv\Scripts\python.exe test_subscription_utc.py
```

Esta suite valida escenarios de:

- Sin suscripción.
- Suscripción activa/expirando.
- Periodo de gracia (10 días).
- Expiración definitiva.
- Independencia de la zona horaria del servidor.
