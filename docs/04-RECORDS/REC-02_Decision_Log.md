# REC-02: Registro de Decisiones Técnicas (ADR)

**Versión:** 1.1 | **Fecha:** 2026-09-24 | **Propietario:** Equipo Técnico

---

## ADR-001: Monolito Full-Stack vs Microservicios

**Fecha:** 2025-11-01  
**Contexto:** Se necesitaba decidir la arquitectura base del proyecto.

**Decisión:** Monolito Full-Stack con Flask.

**Consecuencias:**
- ✅ Desarrollo más rápido al inicio
- ✅ Despliegue simple (un solo servidor)
- ✅ Sin complejidad de red/comunicación entre servicios
- ❌ Escalabilidad limitada (todo escala junto)
- ❌ Stack tecnológico único (no se puede mezclar tecnologías)

---

## ADR-002: UTC como Única Zona Horaria

**Fecha:** 2026-03-01  
**Contexto:** Bugs causados por comparaciones de fechas entre servidor, BD y cliente en diferentes zonas horarias.

**Decisión:** Todas las fechas se almacenan y comparan exclusivamente en UTC.

**Consecuencias:**
- ✅ Elimina bugs de zona horaria
- ✅ Consistencia entre backend y BD
- ✅ Implementación via `AwareDateTime` type decorator en SQLAlchemy
- ❌ Presentación al usuario requiere conversión UTC → local en frontend
- ❌ Todos los desarrolladores deben recordar usar `datetime.now(timezone.utc)`

---

## ADR-003: Base de Datos como Fuente de Verdad para Auth

**Fecha:** 2026-01-15  
**Contexto:** Clerk se adoptó como OAuth provider. Se necesitaba definir la relación entre Clerk y la BD local para autenticación.

**Decisión:** Clerk es el proveedor de identidad, pero la BD local es el sistema de registro autoritativo. Sin registro en BD → sin acceso.

**Consecuencias:**
- ✅ Clerk puede cambiarse sin perder usuarios
- ✅ Control total sobre permisos y roles
- ✅ Auto-creación de usuarios con trial
- ❌ Latencia adicional (validar JWT + consultar BD)
- ❌ Complejidad de sincronización Clerk ↔ BD

---

## ADR-004: Doble Blueprint (Web + API)

**Fecha:** 2026-01-15  
**Contexto:** Necesidad de servir tanto un dashboard web HTML como APIs JSON para clientes externos (Scanner IA, app móvil).

**Decisión:** Cada dominio tiene dos blueprints: uno web (HTML) y uno API (JSON), compartiendo la misma capa de servicios.

**Consecuencias:**
- ✅ Código compartido en servicios (DRY)
- ✅ Versionado independiente posible en el futuro
- ✅ CSRF seguro para web, exento para API
- ❌ Mayor cantidad de archivos de rutas
- ❌ Posible divergencia si no se mantiene sincronizado

---

## ADR-005: Rate Limiting Inteligente vs Punitivo

**Fecha:** 2026-03-01  
**Contexto:** El sistema antiguo castigaba a todos los usuarios con 90 segundos de espera, causando frustración.

**Decisión:** Sistema inteligente que diferencia entre usuarios legítimos (12s) y patrones de spam (30s).

**Consecuencias:**
- ✅ Mejor experiencia para usuarios reales
- ✅ Detección de abusos
- ❌ Almacenamiento en memoria (se pierde al reiniciar)
- ❌ No escala horizontalmente sin Redis

---

## ADR-006: Enfoque de Tokens AI (Velzia 2.0.0)

**Fecha:** 2026-04-14  
**Contexto:** Integración con Scanner IA requiere un sistema de créditos para controlar uso del servicio.

**Decisión:** Sistema de wallets por usuario con plan_tokens (mensuales) + extra_tokens (comprados).

**Consecuencias:**
- ✅ Control de uso por plan (Elite ilimitado, otros limitados)
- ✅ Monetización via top-ups
- ✅ Anti-duplicado por mp_payment_id
- ❌ Complejidad de reseteo mensual de tokens
- ❌ Lógica de descuento (primero plan, luego extra) no es obvia

---

## ADR-007: Servicios con @staticmethod y Tuplas (result, error)

**Fecha:** 2026-03-01  
**Contexto:** Necesidad de un patrón consistente para separar lógica de negocio de rutas.

**Decisión:** Servicios como clases con métodos `@staticmethod` que retornan `(resultado, None)` o `(None, error_dict)`.

**Consecuencias:**
- ✅ Consistente en todo el códigobase
- ✅ Fácil de testear (sin estado de instancia)
- ✅ Manejo de errores predecible
- ❌ Sin inyección de dependencias
- ❌ Dificultad para mockear en tests complejos

---

## ADR-008: Período de Gracia de 14 Días

**Fecha:** 2026-03-01  
**Contexto:** Usuarios perdían acceso inmediato al expirar la suscripción, causando tickets de soporte.

**Decisión:** Grace period de 14 días post-expiración con acceso de solo lectura.

**Consecuencias:**
- ✅ Reduce tickets de soporte por pagos atrasados
- ✅ Retiene usuarios que olvidaron renovar
- ❌ Complejidad adicional en cálculo de estado
- ❌ Posible abuso (usuarios que no pagan pero siguen accediendo)

---

## ADR-009: No Implementar el Service Worker aún

**Fecha:** 2026-06-16  
**Contexto:** Workbox está en dependencias pero el service worker no está implementado.

**Decisión:** Aplazar implementación del SW hasta la próxima iteración. Priorizar funcionalidad core.

**Consecuencias:**
- ✅ Menos complejidad ahora
- ✅ Enfoque en funcionalidades core
- ❌ Sin PWA instalable
- ❌ Sin caché offline de recursos

---

## ADR-010: Sin Banner de Cookies — Solo Cookies Estrictamente Necesarias

**Fecha:** 2026-09-24  
**Contexto:** Auditoría de cumplimiento legal (LEG-01). La plataforma no usa analítica de terceros ni cookies publicitarias; solo cookies de sesión propias y localStorage del carrito. En Colombia no se exige banner de consentimiento para cookies estrictamente necesarias.

**Decisión:** No implementar banner de cookies. El aviso informativo vive en `/legal#privacidad` y `/legal#datos`. Gate: cualquier futuro script de analítica/publicidad exige PRIMERO banner con opt-in y actualización de políticas, DESPUÉS activación.

**Consecuencias:**
- ✅ Cero fricción en el menú público
- ✅ Cumplimiento vigente sin código adicional
- ❌ El gate depende de disciplina del equipo (documentado en LEG-01 §3)

---

## ADR-011: Consentimiento de Datos — Checkbox Solo en el Registro, Aviso Informativo en Formularios Públicos

**Fecha:** 2026-09-24 (revisada el mismo día tras prueba de UX)  
**Contexto:** Los formularios públicos (checkout y reservas) recolectan datos personales de clientes del restaurante. Una primera implementación agregó checkbox obligatorio de autorización en cada formulario + validación en backend, pero mataba la conversión: en un checkout de 3 toques, un checkbox adicional con texto legal es fricción injustificada para un pedido de $15.000 (decisión explícita del titular: "no vamos al extremo").

**Decisión:**
- **Registro (`accept_terms`):** mantiene el checkbox obligatorio validado en servidor (aquí sí hay contrato de suscripción y aceptación de términos).
- **Checkout y reservas públicas:** SIN checkbox. En su lugar, una línea informativa discreta bajo el botón: "Tus datos se usan solo para procesar y entregar tu pedido" / "Usamos tu nombre y WhatsApp solo para gestionar esta reserva". Finalidad informada, cero fricción.
- **Backend:** sin gate de `consent_data` (se implementó y se revirtió el mismo día; `app/routes/public.py` queda como estaba).

**Consecuencias:**
- ✅ Checkout limpio: nombre + teléfono + confirmar, nada más
- ✅ Deber de información cumplido (finalidad visible en el formulario y en `/legal#privacidad`)
- ❌ No hay autorización expresa clic a clic en el menú público; si asesoría legal o la SIC la exigiera, reactivar el gate (el diseño completo quedó documentado en el historial de este ADR y en LEG-01)
- ❌ La autorización del registro no alcanza a los comensales (quienes aceptan son los restaurantes, como responsables del tratamiento de SUS clientes)

---

## Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial (9 ADRs) | Auditoría Documental |
| 2026-09-24 | 1.1 | ADR-010 y ADR-011 (cumplimiento legal LEG-01) | Buffy (agente) |
