# Flujo n8n — Recordatorios de Suscripción

## Descripción

Workflow en n8n que verifica restaurantes con suscripción próxima a vencer y envía correos de recordatorio (días 5, 2 y 1 antes del vencimiento).

## Componentes

### API Endpoint (Flask)

```
POST /api/email/pending-reminders
Headers:
  x-api-key: <SERVICE_API_KEY>
```

- **Ruta:** `app/routes/api_email.py`
- **Método:** `POST` (requiere API key)
- **Autenticación:** `x-api-key` debe coincidir con `SERVICE_API_KEY` del `.env`
- **CSRF:** Exenta (blueprint exempted vía `csrf.exempt()` en `app/__init__.py`)
- **Retorna:** JSON con lista de recordatorios pendientes

#### Response (200 OK)

```json
{
  "success": true,
  "data": [
    {
      "email": "dueno@restaurante.com",
      "subject": "Tu suscripcion vence manana - Velzia",
      "html": "<!DOCTYPE html>...",
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
- Diseño responsive con botón de "Renovar ahora" y plan actual

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

## Workflow en n8n

### Schedule Trigger
- **Frecuencia:** Diario, 8:00 AM (UTC-5 / Colombia)
- **Cron:** `0 13 * * *` (13:00 UTC = 8:00 AM Colombia)

### HTTP Request
```
Method: POST
URL: http://orderfox:5000/api/email/pending-reminders
Authentication: Header
  Key: x-api-key
  Value: <SERVICE_API_KEY>
```

### Loop over Items
Para cada recordatorio en `data`:

### Gmail SMTP
```
To: {{ $json.email }}
Subject: {{ $json.subject }}
Body (HTML): {{ $json.html }}
```

### Manejo de errores
Si el endpoint Flask falla → n8n reintenta 2 veces con 5 min de espera.

---

## Configuración en Docker

Si Orderfox corre en Docker, n8n debe estar en la misma red Docker:

```
orderfox-net (network)
├── orderfox (puerto 5000)
└── n8n (llama a: http://orderfox:5000/api/email/pending-reminders)
```

### Agregar n8n a la red compartida

```bash
docker network connect orderfox-net n8n
```

Si n8n se levanta con docker-compose, agregar:

```yaml
networks:
  - orderfox-net
```

---

## Variables de Entorno Requeridas

| Variable | Dónde se usa |
|----------|-------------|
| `SERVICE_API_KEY` | Autenticación del webhook (Flask + n8n) |
| `BASE_URL` | URLs de renovación en el email |
| `DATABASE_URL` | Conexión a MySQL (Orderfox) |

---

## Prueba manual

```bash
curl -X POST http://localhost:5000/api/email/pending-reminders \
  -H "x-api-key: <SERVICE_API_KEY>"
```
