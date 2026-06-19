# PROC-02: Plan de Respuesta a Incidentes

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Clasificación de Incidentes

| Severidad | Nombre | Definición | Tiempo de Respuesta |
|-----------|--------|------------|---------------------|
| **S1** | Crítico | Sistema caído o inaccesible para todos los usuarios | Inmediato (< 15 min) |
| **S2** | Alto | Funcionalidad principal afectada (pedidos, pagos) | < 30 min |
| **S3** | Medio | Funcionalidad secundaria afectada (dashboard, reportes) | < 2 horas |
| **S4** | Bajo | Bug cosmético o funcionalidad no crítica | < 24 horas |

---

## 2. Canales de Comunicación

| Canal | Propósito | Enlace |
|-------|-----------|--------|
| `#incidents` | Slack/Discord del equipo | Comunicación en vivo |
| `soporte@velzia.com` | Reportes de usuarios | Soporte al cliente |
| GitHub Issues | Seguimiento post-mortem | Repositorio del proyecto |

---

## 3. Runbook por Tipo de Incidente

### 3.1 S1: Sistema Caído (500 Error)

**Síntomas:** Todos los usuarios ven error 500 al cargar cualquier página.

**Pasos:**
1. Verificar salud del servidor:
   ```bash
   curl -I https://tudominio.com
   systemctl status orderfox
   journalctl -u orderfox -n 50 --no-pager
   ```

2. Verificar conexión a base de datos:
   ```bash
   python -c "from app import create_app; app=create_app(); app.app_context().push(); from app.extensions import db; db.engine.connect()"
   ```

3. Verificar espacio en disco:
   ```bash
   df -h
   ```

4. Si la BD está caída:
   ```bash
   systemctl status mysql
   systemctl restart mysql
   ```

5. Si el servidor web está caído:
   ```bash
   systemctl restart orderfox
   systemctl restart nginx
   ```

6. Si no se resuelve en 15 min → escalar a equipo senior.

### 3.2 S2: Fallo en Procesamiento de Pedidos

**Síntomas:** Usuarios no pueden crear pedidos o pedidos no llegan al dashboard.

**Pasos:**
1. Revisar logs de la aplicación:
   ```bash
   journalctl -u orderfox -n 100 --no-pager | grep ERROR
   ```

2. Verificar integridad de la tabla `orders`:
   ```bash
   mysql -u root -p orderfox -e "SELECT status, COUNT(*) FROM orders GROUP BY status;"
   ```

3. Verificar conexión con Scanner IA (si aplica):
   ```bash
   curl -X POST https://scanner-ia-url/health -H "x-api-key: $SERVICE_API_KEY"
   ```

4. Verificar rate limiter (posible falso positivo):
   ```bash
   # Revisar si hay IPs bloqueadas
   # El rate limiter es in-memory, reiniciar el servicio lo limpia
   systemctl restart orderfox
   ```

### 3.3 S2: Fallo en Pagos (Mercado Pago)

**Síntomas:** Usuarios no pueden pagar suscripciones o top-ups.

**Pasos:**
1. Verificar credenciales de MP:
   ```bash
   # Verificar que MP_ACCESS_TOKEN está configurado
   grep MP_ACCESS_TOKEN /var/www/orderfox/.env
   ```

2. Verificar estado del webhook:
   ```bash
   # Revisar que el webhook de MP está configurado correctamente
   curl -I https://tudominio.com/api/webhook/mp
   ```

3. Verificar idempotencia en tabla `ai_token_transactions`:
   ```sql
   SELECT mp_payment_id, COUNT(*) FROM ai_token_transactions GROUP BY mp_payment_id HAVING COUNT(*) > 1;
   ```

4. Si es error de MP: revisar dashboard de Mercado Pago.

### 3.4 S3: Autenticación Fallando

**Síntomas:** Usuarios no pueden iniciar sesión (Clerk o tradicional).

**Pasos:**
1. Verificar que Clerk responde:
   ```bash
   curl -I https://oriented-tortoise-50.clerk.accounts.dev
   ```

2. Verificar credenciales de Clerk en `.env`:
   ```bash
   grep CLERK_ /var/www/orderfox/.env
   ```

3. Revisar tabla `users`:
   ```sql
   SELECT COUNT(*), clerk_id IS NOT NULL as has_clerk FROM users GROUP BY has_clerk;
   ```

4. Verificar que JWT_SECRET_KEY coincide con CLERK_SECRET_KEY (si se usa JWT).

### 3.5 S3: Lentitud General

**Síntomas:** Páginas tardan >5s en cargar.

**Pasos:**
1. Verificar uso de CPU/memoria:
   ```bash
   top -b -n 1 | head -20
   free -h
   ```

2. Verificar consultas lentas en MySQL:
   ```bash
   mysql -u root -p -e "SHOW FULL PROCESSLIST;"
   ```

3. Verificar número de workers de Gunicorn:
   ```bash
   ps aux | grep gunicorn | wc -l
   ```

4. Ajustar workers si es necesario (regla general: 2-4 × núcleos de CPU).

---

## 4. Plantilla de Post-Mortem

Para incidentes S1 o S2 con downtime >1 hora, crear un issue en GitHub con esta plantilla:

```markdown
## Post-Mortem: [Título del Incidente]

**Fecha:** YYYY-MM-DD | **Duración:** Xh Xm
**Severidad:** S1/S2 | **Impacto:** [usuarios afectados]

### Línea de Tiempo
- HH:MM — [Evento inicial]
- HH:MM — [Detección]
- HH:MM — [Acción tomada]
- HH:MM — [Resolución]

### Causa Raíz
[Descripción clara de por qué ocurrió]

### Acciones Tomadas
- [Acción 1]
- [Acción 2]

### Acciones Preventivas
- [ ] [Issue #] — [Descripción de la mejora]
- [ ] [Issue #] — [Monitoreo o alerta a agregar]

### Lecciones Aprendidas
[Qué haríamos diferente]
```

---

## 5. Escalación

| Rol | Contacto | Disponibilidad |
|-----|----------|----------------|
| Desarrollador Senior | Slack @senior-dev | 9-18, Lu-Vi |
| DevOps | Slack @devops | 9-18, Lu-Vi |
| Emergencia (S1 fuera de horas) | Teléfono +573000000000 | 24/7 |

---

## 6. Mejora Continua

- Después de cada S1/S2 → post-mortem en 48 horas
- Revisión trimestral de este runbook
- Simulacro de incidente S1 cada 6 meses

---

## 7. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
