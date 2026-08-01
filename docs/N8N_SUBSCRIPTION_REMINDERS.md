# Recordatorios de Suscripción

## Descripción

Sistema que detecta restaurantes con suscripción próxima a vencer y envía correos de recordatorio (días 5, 2 y 1 antes del vencimiento).

> **Migración (2026-08-01):** Antes este flujo lo orquestaba n8n (Schedule Trigger → `POST /api/email/pending-reminders` → Gmail SMTP). Ahora vive 100% en Flask: **APScheduler** corre la lógica y **`mail_service`** envía los correos. n8n/ngrok ya no son necesarios.

## Componentes

### Lógica de negocio — `app/services/reminder_service.py`

- `build_subscription_reminders()` → devuelve la lista de recordatorios pendientes (misma forma que devolvía el endpoint).
- `send_subscription_reminders()` → construye y envía cada recordatorio por email vía `mail_service.send_email()`. Devuelve cuántos se enviaron.

### Tarea programada — `app/tasks.py`

```
send_subscription_reminders
  trigger: cron, hour=13, minute=0 (UTC)  →  8:00 AM Colombia
```

Se registra en `init_tasks(scheduler)` junto a las demás tareas de APScheduler (expiración de pedidos, cupones, etc.).

### API Endpoint (deprecado, por compatibilidad)

```
POST /api/email/pending-reminders
Headers:
  x-api-key: <SERVICE_API_KEY>
```

- **Ruta:** `app/routes/api_email.py`
- **Método:** `POST` (requiere API key)
- **Estado:** **[DEPRECADO]** — el envío ya no depende de este endpoint; se mantiene para no romper flujos externos. Retorna la misma respuesta JSON de antes.

#### Response (200 OK)

```json
{
  "success": true,
  "data": [
    {
      "email": "dueno@restaurante.com",
      "subject": "Tu suscripcion vence manana - Velzia",
      "html": "<!DOCTYPE html>...",
      "text": "Tu suscripcion de Mi Restaurante expira manana...",
      "restaurant_name": "Mi Restaurante",
      "days_remaining": 1,
      "plan_name": "Plan Emprendedor",
      "plan_price": "30.000"
    }
  ],
  "count": 1
}
```

### Template HTML

- **Archivo:** `app/template/email/subscription_reminder.html`
- Variables: `restaurant_name`, `title`, `message`, `renew_url`, `plan_name`, `plan_price`

### PLAN_PRICES

| Plan | Precio |
|------|--------|
| `emprendedor` | $30.000/mes |
| `crecimiento` | $40.000/mes |
| `elite` | $50.000/mes |
| `trial` (u otros) | Gratis |

### Días de recordatorio

- **5 días** → "Tu suscripcion vence pronto"
- **2 días** → "Tu suscripcion vence en 2 dias"
- **1 día** → "Tu suscripcion vence manana"

---

## Configuración de Correo (Gmail SMTP)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `MAIL_SERVER` | `smtp.gmail.com` | Servidor SMTP |
| `MAIL_PORT` | `587` | 587 para TLS, 465 para SSL |
| `MAIL_USE_TLS` | `True` | Usar TLS |
| `MAIL_USERNAME` | — | Cuenta Gmail de envío |
| `MAIL_PASSWORD` | — | Contraseña de aplicación Gmail ([Google App Passwords](https://myaccount.google.com/apppasswords)) |
| `MAIL_DEFAULT_SENDER` | `MAIL_USERNAME` | Remitente por defecto |

### Regla importante

> Gmail requiere **app-specific password** (contraseña de aplicación), no la contraseña normal de la cuenta. TLS por defecto.

---

## Variables de Entorno Requeridas

| Variable | Dónde se usa |
|----------|-------------|
| `MAIL_USERNAME` / `MAIL_PASSWORD` | Envío de los correos |
| `BASE_URL` | URLs de renovación en el email |
| `DATABASE_URL` | Conexión a MySQL (Orderfox) |

---

## Prueba manual

El scheduler corre solo, pero puedes probar el envío directamente:

```bash
python -c "from app import create_app; from app.services.reminder_service import send_subscription_reminders; app=create_app(); app.app_context().push(); print('enviados:', send_subscription_reminders())"
```

O consultar los pendientes sin enviar (endpoint deprecado):

```bash
curl -X POST http://localhost:5000/api/email/pending-reminders \
  -H "x-api-key: <SERVICE_API_KEY>"
```
