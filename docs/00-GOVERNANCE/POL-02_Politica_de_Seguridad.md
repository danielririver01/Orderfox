# POL-02: Política de Seguridad

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Propósito

Establecer las normas y prácticas de seguridad para proteger los datos de los restaurantes, sus clientes, y la infraestructura de Orderfox.

---

## 2. Reporte de Vulnerabilidades

Si encuentras una vulnerabilidad de seguridad en Orderfox:

1. **No** crear un Issue público en GitHub
2. Enviar un email a `soporte@velzia.com` con:
   - Descripción del problema
   - Pasos para reproducir
   - Posible impacto
   - Sugerencia de solución (opcional)
3. Esperar confirmación antes de divulgar públicamente

**Tiempo de respuesta esperado:** < 48 horas hábiles.

---

## 3. Prácticas de Seguridad en el Código

### 3.1 Contraseñas
- Nunca almacenadas en texto plano
- Hasheadas con `werkzeug.security.generate_password_hash()`
- Política de mínimo 8 caracteres

### 3.2 Variables de Entorno
- Ningún secreto en el código fuente
- Usar archivo `.env` (excluido via `.gitignore`)
- Rotar claves comprometidas inmediatamente

### 3.3 Base de Datos
- Escapar inputs: usar SQLAlchemy (ORM), no SQL crudo
- Pool de conexiones con `pool_pre_ping=True`
- Usuario de BD con permisos mínimos necesarios

### 3.4 APIs
- CSRF: web protegido por Flask-WTF, API exento
- JWT validado contra Clerk (no confianza implícita)
- API Key única por servicio integrado
- Rate limiting en endpoints de pedidos

### 3.5 Frontend
- Cookies HttpOnly + SameSite
- Content Security Policy configurada

---

## 4. Manejo de Datos Sensibles

| Tipo de Dato | ¿Se Almacena? | ¿Encriptado? | Retención |
|-------------|---------------|--------------|-----------|
| Contraseñas | ✅ (hash) | ✅ (Werkzeug) | Indefinido |
| Emails | ✅ | ❌ (texto plano) | Hasta eliminación de cuenta |
| Teléfonos | ✅ | ❌ (texto plano) | Hasta eliminación de cuenta |
| Direcciones IP | ✅ | ❌ (texto plano) | 24h (rate limiting) |
| API Keys | ✅ (en BD) | ❌ (texto plano) | Indefinido |
| Pagos MP | ❌ | N/A | Procesado via MP, no almacenado |

---

## 5. Checklist de Seguridad para Pull Requests

- [ ] ¿El PR expone información sensible en logs?
- [ ] ¿Usa ORM en vez de SQL crudo?
- [ ] ¿Las rutas nuevas tienen autenticación?
- [ ] ¿Los endpoints POST/PUT/DELETE tienen CSRF (web) o exención justificada (API)?
- [ ] ¿Se validan los datos de entrada?
- [ ] ¿No hay secretos hardcodeados?

---

## 6. Procedimiento en Caso de Brecha

1. **Contener:** Desconectar servicio o revocar credenciales comprometidas
2. **Investigar:** Revisar logs, determinar alcance
3. **Notificar:** Informar a usuarios afectados dentro de 72 horas
4. **Remediar:** Corregir vulnerabilidad, rotar todas las claves
5. **Post-mortem:** Documentar causa raíz y medidas preventivas

---

## 7. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
