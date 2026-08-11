# 🔍 Informe de Auditoría de Orderfox

**Fecha:** 11 de agosto de 2026
**Alcance:** Dashboard, menú público, pedidos, caja registradora, CRUD, Copilot VZ (DeepSeek)
**Método:** Pruebas manuales por API con sesión real + suite de tests automatizados (pytest)

---

## 🎯 Resumen ejecutivo

| Área | Resultado |
|---|---|
| **Bugs encontrados** | 2 (ambos corregidos y verificados) |
| **Auditorías manuales** | 5 módulos — todos aprobados |
| **Tests automatizados** | 313/313 pasando · cobertura 50.8% (requerido: 35%) |
| **Datos de prueba** | Eliminados al finalizar · token de IA restaurado |
| **Estado final** | Sistema sano y limpio |

---

## 🐛 Bugs encontrados y corregidos

### Bug 1 — Página "Productos" del dashboard (error 500)

- **Síntoma:** `GET /dashboard/Productos` devolvía HTTP 500
- **Causa raíz (doble):**
  1. La ruta renderizaba `dashboard/productos.html`, pero la plantilla real se llama `products.html` (nunca existió `productos.html`)
  2. Aunque se corrigiera el nombre, la ruta no pasaba las variables que la plantilla necesita (`products`, `categories`, `plan_limits`, etc.)
- **Solución:** La página canónica ya existía y funcionaba en `/products/` → la ruta rota ahora **redirige a ella** (reutiliza código existente, sin duplicar lógica)
- **Archivo:** `app/routes/dashboard.py` (ruta `/Productos`)

### Bug 2 — CRÍTICO: ningún pedido del menú público se podía crear

- **Síntoma:** Al crear un pedido desde el menú: *"Los productos seleccionados ya no están disponibles"* — siempre, para todos los restaurantes
- **Causa raíz:** Las claves del carrito llegan como **texto** desde el navegador (`"2"`, `"3"` — así funciona JSON), pero el servidor construía el mapa de productos con claves **enteras** (`2`, `3`). La búsqueda `products_map.get("2")` fallaba siempre:
  ```python
  products_map = {2: producto, 3: producto}   # claves enteras
  products_map.get("2")                       # → None (¡no coincide!)
  ```
- **Consecuencia:** **ningún pedido del menú público se podía crear**. Afectaba a todos los restaurantes, no solo a Felicia
- **Solución:** Normalizar las claves del carrito a entero antes de buscar
- **Archivo:** `app/services/public_menu_service.py` (`create_order_from_cart`)
- **Importante:** si el menú está en producción, este arreglo debe desplegarse

---

## ✅ Auditorías por módulo

### 1. Dashboard (8/8 páginas, 6/6 APIs)

| Página | Estado |
|---|---|
| `/dashboard/` (Panel) | ✅ 200 |
| `/cash-register/` (Centro de Caja) | ✅ 200 |
| `/categories/` (Categorías) | ✅ 200 |
| `/insights/` (Copilot VZ) | ✅ 200 |
| `/orders/` (Pedidos) | ✅ 200 |
| `/dashboard/subscription` | ✅ 200 |
| `/dashboard/ai-scan` | ✅ 200 |
| `/dashboard/Productos` | ✅ 200 (tras corrección, redirige a `/products/`) |

APIs verificadas: overview, stats, check-orders, orders, products (10), categories.

### 2. Menú público + flujo de pedido (punto a punto)

| Paso | Resultado |
|---|---|
| Página del menú (`/felicia/`, Astro 4321) | ✅ 200 en 29 ms |
| API del menú (`/api/public/menu/felicia`) | ✅ 200 — 5 categorías, 10 productos |
| `init-checkout` (anti-bots, 3s) | ✅ Sesión iniciada |
| Crear pedido (2x Calentado + 1x Tamal) | ✅ **ORD-001 · $48.000** (tras corregir Bug 2) |
| ¿Aparece en el dashboard? | ✅ Sí, con estado pendiente |

### 3. Caja registradora (9 comprobaciones, 0 bugs)

| Prueba | Resultado |
|---|---|
| Resumen del día | ✅ 200 |
| ⚠️ Cerrar sin ventas | ✅ 400 — *"No hay ventas en este periodo"* |
| Pagar pedido en efectivo ($50.000 recibidos) | ✅ **Vuelto calculado: $2.000** |
| Métricas tras pago (avg_ticket $48.000) | ✅ Correctas |
| Pedidos pagados del día | ✅ ORD-001 con su vuelto |
| Cierre de caja | ✅ Cierre creado |
| ⚠️ Cierre duplicado | ✅ 409 — *"Ya cerraste caja para el periodo"* |
| Historial de cierres | ✅ Con total y vuelto |
| Ticket imprimible | ✅ "Cierre de caja · Felicia" |

**Protecciones verificadas:** no se puede cerrar sin ventas, no se puede cerrar dos veces el mismo periodo, CSRF rechaza POSTs sin token.

### 4. CRUD de productos y categorías (29/29 comprobaciones)

- **Categorías:** crear, leer, editar, desactivar/reactivar, reordenar, eliminar — ✅ todos
- **Productos:** crear, leer, edición parcial y completa, desactivar/reactivar (filtro `active_only` verificado), eliminar — ✅ todos
- **Caminos de error:** crear sin nombre/precio (400), editar/leer/eliminar inexistentes (404), categoría inexistente (400) — ✅ todos
- **🛡️ Protección de integridad:** eliminar una categoría con productos → **400 bloqueado** (*"No puedes eliminar esta categoría porque tiene 1 producto(s) asociado(s)"*). Se debe eliminar primero el producto
- **Limpieza:** la base quedó exactamente como estaba (5 categorías, 10 productos)

### 5. Copilot VZ / Insights (llamada real a DeepSeek)

| Prueba | Resultado |
|---|---|
| Onboarding/madurez de datos | ✅ Nivel 2 (con catálogo + ventas) |
| Consulta rápida (SQL, gratis) | ✅ 0 créditos, con gráfico |
| **Análisis IA → DeepSeek real** | ✅ 11.5s, `deepseek-v4-flash`, recomendaciones + gráfico |
| Seguimiento (follow-up) | ✅ Gratis (0 créditos) |
| Renombrar / fijar (pin) | ✅ 200 |
| Errores (mensaje vacío, conversación inexistente) | ✅ 400 / 404 |
| Business events (pending/consume/dismiss) | ✅ Correctos |
| Telemetría (`ai_llm_calls`) | ✅ 2 llamadas registradas |

**Hallazgos positivos del código:**
- Estado vacío inteligente: sin catálogo o ventas → responde con guías **sin gastar tokens ni llamar a DeepSeek**
- Consumo correcto: solo el primer análisis consume; seguimientos gratis hasta el tope
- Lock pesimista (`SELECT ... FOR UPDATE`) en el wallet → previene dobles cobros
- Telemetría silenciosa (no rompe el flujo si falla el registro)

---

## 🧪 Suite de tests automatizados

```
✅ 313 tests PASADOS
✅ 0 fallos
✅ Cobertura: 50.8% (requerido: 35%)
```

Módulos cubiertos: caja registradora, pagos, límites de suscripción, rate limiter, Copilot, subida de imágenes, servicios, etc.

---

## 🔒 Notas de seguridad

- Los POSTs del dashboard requieren token CSRF (verificado: rechazados sin token) ✅
- Los endpoints de insights son CSRF-exempt (por diseño, usan sesión) — considerar revisión futura
- La cookie de sesión compartida en el chat fue de servidor local; se recomendó cerrar sesión/reiniciar

---

## 🧹 Limpieza realizada al finalizar

| Dato de prueba | Acción |
|---|---|
| Conversación "Auditoria VZ Final" + 6 mensajes | Eliminada |
| 2 registros de telemetría LLM | Eliminados |
| Pedido ORD-001 "Cliente Prueba" ($48.000) + 2 items | Eliminado |
| Cierre de caja del 11/08 ($48.000) | Eliminado |
| Transacción de token `copilot_vz` | Eliminada + **token restaurado al wallet** |

**Wallet final:** 44 tokens plan / 6 usados (idéntico al estado previo a la auditoría).

Los datos semilla del proyecto (pedidos VZ, cierres históricos, conversaciones demo) **no se tocaron**.

---

## 🖥️ Estado de los servidores

- Flask (puerto 5000): **detenido**
- Astro / menú (puerto 4321): **detenido**

Para reiniciar:
```bash
# Flask (desde Orderfox/)
.venv/Scripts/python run.py

# Astro (desde Orderfox/astro/)
npm run dev
```

---

## 📁 Archivos modificados en esta sesión

| Archivo | Cambio |
|---|---|
| `app/routes/dashboard.py` | Ruta `/Productos` redirige a la página canónica `/products/` |
| `app/services/public_menu_service.py` | Normalización de claves del carrito (string → int) — **bug crítico de pedidos** |
