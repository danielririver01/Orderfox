# Análisis DOFA — Orderfox / Velzia

**Fecha:** Agosto 2026
**Producto:** Plataforma SaaS de gestión de pedidos para restaurantes colombianos
**Versión:** 1.4.x

---

## Fortalezas (Internas, Positivas)

1. **Producto completo y funcional en producción** — Menú digital (frontend Astro SSR), pedidos por código QR, mesas, cash register, panel del dueño, notificaciones y pagos en línea. No es un prototipo; corre en producción con CI.

2. **Doble diferenciador con Inteligencia Artificial** — Dos motores de IA que ningún competidor colombiano ofrece:
   - **Copilot VZ**: asistente conversacional con clasificador híbrido (consultas `quick` directas a SQL + análisis profundo con DeepSeek), wallet de tokens, compresión de contexto en 2 fases y prompt versionado.
   - **Scanner IA**: escáner de facturas/compras para control de gastos (servicio externo integrado vía JWT/API key).

3. **Ingresos recurrentes en dos frentes** — Suscripción mensual (4 planes: Trial 90 días, Emprendedor, Crecimiento, Élite) + recargas de tokens IA. El pago con Mercado Pago es idempotente (webhooks con verificación de firma HMAC-SHA256 y protección de race conditions).

4. **Seguridad auditada y endurecida** — Suite de seguridad activa: k6 (headers + JWT audit), OWASP ZAP (DAST), Gitleaks (secretos, pre-commit), Trivy (Docker), pip-audit/npm audit (0 HIGH). Locks pesimistas `SELECT FOR UPDATE` cierran TOCTOU en tokens IA y pagos.

5. **Calidad de código creciente** — 289+ tests automatizados, refactor en capas (routes → services), templates sin CSS/JS inline (factorizados), regla de calidad obligatoria en AGENTS.md. Los tests corren contra SQLite en local y MySQL en CI.

6. **Protección contra bots y spam en pedidos** — Rate limiter (3/min por IP + ban), honeypot, mínimo 3s entre checkout y envío, validación de carrito vacío. Los clientes reales nunca tienen problemas.

7. **Pensado para Colombia** — Mercado Pago (pasarela líder), precios en COP con formato colombiano, interfaz en español, notificaciones vía ntfy.sh sin costo por SMS, y soporte de zona horaria de Colombia (UTC + helpers de conversión).

8. **Prueba gratuita sin riesgo** — 90 días gratis con todas las funciones, sin tarjeta de crédito, con sistema anti-reuso de trial por email/WhatsApp (TrialHistory).

9. **Un restaurante por cuenta con aislamiento** — Cada negocio tiene su espacio, menú, mesas y configuración propios.

10. **Fidelización y retención** — Sorpresa Velzia (caja sorpresa con recompensas, rate limit + expiración + UUID), logros con tokens extra, recordatorios de renovación por email (5/2/1 días) y cancelación/eliminación de pedidos entregados.

---

## Debilidades (Internas, Negativas)

1. **Cobertura de tests aún parcial** — Aunque hay 289+ tests, la cobertura global ronda ~30-35%. Muchas rutas nuevas (cash register, rewards, insights) todavía dependen de pruebas manuales.

2. **Rate limiter en memoria** — Se pierde al reiniciar el servidor y no escala horizontalmente. Sin Redis, es vulnerable bajo balanceadores múltiples.

3. **Sin sistema de colas de tareas** — APScheduler ejecuta tareas en el mismo proceso; las notificaciones y webhooks son síncronos con `requests` (timeout de 10s pueden ralentizar la respuesta del pedido).

4. **Subida de imágenes sin auto-limpieza** — `app/static/uploads/` acumula caché local sin limpieza automática.

5. **Scanner IA oculto por defecto** — Los enlaces de Scanner solo aparecen cuando `SCANNER_IA_URL` está configurado (para ahorrar costos), lo que en la práctica deja el diferenciador invisible para muchos usuarios.

6. **Lógica duplicada restante** — Aún hay pequeños solapamientos entre versiones web y API (ej. validaciones de perfil en `dashboard.py` y `api_dashboard.py`).

7. **Sin PWA del dashboard activa** — El registro de service worker solo se usa para notificaciones en tiempo real de pedidos; la estrategia offline/PWA documentada (Workbox, Dexie) no está plenamente activa para los dueños.

8. **Configuración desactualizada en el código** — `settings.APP_VERSION` no está sincronizado con los tags de git (gotcha documentado en AGENTS.md).

---

## Oportunidades (Externas, Positivas)

1. **Digitalización de restaurantes en Colombia** — El mercado de menús digitales y pedidos online crece; los restaurantes pequeños-medianos son el foco.

2. **Crecimiento de pagos digitales** — Mercado Pago, Nequi y Daviplata se adoptan masivamente; cada vez menos efectivo en la caja.

3. **IA como ventaja competitiva real** — Copilot VZ + Scanner IA posicionan a Velzia como innovador frente a competidores con menús básicos. Copilot ya maneja español, precios colombianos y contexto del negocio.

4. **Integración con WhatsApp Business API** — Canal dominante en Colombia. Notificaciones y confirmaciones de pedidos por WhatsApp aumentarían la retención de dueños.

5. **Expansión regional** — Modelo replicable en Perú, México y Chile adaptando la pasarela de pagos.

6. **Nuevas fuentes de ingreso** — Inventario, gestión de empleados, reportes avanzados, integración con mensajerías para domicilios, y la caja registradora como posible módulo premium.

7. **Tokens IA como ingreso recurrente adicional** — Recargas de tokens para Copilot VZ/Scanner generan ingresos fuera de la suscripción.

8. **Crecimiento por recomendación** — Los dueños de restaurantes se recomiendan entre sí; un programa de referidos traería clientes sin publicidad.

9. **Marketplace de restaurantes** — Un directorio para que clientes descubran restaurantes (tipo Rappi, pero para dueños) como meta a futuro.

10. **PWA del dashboard** — Activar el service worker permitiría a los dueños "instalar" Velzia como app sin desarrollo nativo.

---

## Amenazas (Externas, Negativas)

1. **Competidores gratuitos** — Google My Business y las páginas de Instagram ofrecen menú digital sin costo; muchos restaurantes lo ven como suficiente.

2. **Gigantes del delivery** — Rappi e iFood podrían sumar menú autogestionado y aplastar a competidores pequeños con su escala.

3. **WhatsApp Business como default** — La mayoría de restaurantes toman pedidos por WhatsApp sin costo; cambiar esa costumbre es difícil.

4. **Sensibilidad al precio** — Incluso $30.000 COP/mes puede ser mucho para microempresas en crisis.

5. **Dependencia de servicios externos** — Clerk, Cloudinary, Mercado Pago, ntfy.sh y DeepSeek pueden cambiar reglas o fallar, afectando el servicio.

6. **Imitación por competidores** — Menú + QR + pedidos es fácil de copiar. La ventaja real es la IA, que también es imitable a mediano plazo.

7. **Costos de IA por cuenta de Velzia** — DeepSeek en análisis profundos y seguimientos corre por cuenta de la plataforma; un uso agresivo sin ingresos proporcionales puede comer el margen.

8. **Riesgo de confianza en pagos** — Un incidente de pago o webhook mal procesado puede hacer que los dueños dejen la plataforma rápido.

9. **Crisis económicas** — Los restaurantes recortan gastos; un SaaS es fácil de cancelar en recesión.

10. **Deuda técnica latente** — Archivos grandes (algunos >800 líneas) y cobertura parcial de tests pueden frenar la velocidad de desarrollo frente a competidores más ágiles.

---

## Estrategias derivadas

### Crecimiento (Fortalezas + Oportunidades)
- **Activar el Scanner IA como argumento de venta** del trial de 90 días: quitarlo de "oculto" cuando haya infraestructura y usarlo como gancho de conversión.
- Usar Copilot VZ como diferenciador en landing y demo (análisis en español + contexto colombiano).
- Integrar WhatsApp Business API para notificaciones/confirmaciones en el canal dominante.
- Aprovechar la prueba de 90 días sin tarjeta para bajar la fricción de compra.

### Mejora (Debilidades + Oportunidades)
- Subir la cobertura de tests al 40-50% (cash register, insights, rewards, pagos).
- Migrar el rate limiter a Redis para escalar horizontalmente.
- Mover notificaciones/webhooks a una cola (Celery/RQ) para no bloquear el request del pedido.
- Sincronizar `APP_VERSION` con los tags de git.
- Activar la PWA del dashboard para dueños.

### Defensa (Fortalezas + Amenazas)
- Invertir continuamente en la IA (Copilot + Scanner) como barrera frente a Google My Business y WhatsApp.
- La protección anti-bots y la validación de carrito vacío son ventajas que los competidores no ofrecen; usarlas en el discurso de venta.
- La integración profunda con Colombia (Mercado Pago, COP, español) protege contra Toast o Square.
- Monitorear el costo real de DeepSeek por usuario para que la IA sea rentable, no un drenaje.

### Supervivencia (Debilidades + Amenazas)
- El riesgo más real es la cobertura de tests parcial combinada con deuda técnica: un bug en producción (ej. pedidos perdidos) puede ahuyentar dueños. Priorizar tests en los flujos de dinero (pago, tokens, pedidos).
- Mantener el pago idempotente y con verificación de firma como estándar; un incidente de pagos es el mayor riesgo de confianza.
- Tener un plan B de pasarela/proveedores para reducir la dependencia de servicios externos.

---

## Conclusión

Velzia/Orderfox evolucionó de "menú digital con IA" a **plataforma operativa completa**: menú Astro, mesas, cash register, pedidos, pagos idempotentes y dos motores de IA (Copilot VZ + Scanner IA). El producto y la ingeniería están en una etapa avanzada y lista para escalar.

La prioridad ya no es escribir más funciones sino **validar el negocio**: activar el Scanner IA como gancho comercial, medir el embudo trial → pago y conseguir los primeros restaurantes de pago recurrentes. En paralelo, subir la cobertura de tests y escalar el rate limiter con Redis para sostener el crecimiento sin tropezar.
