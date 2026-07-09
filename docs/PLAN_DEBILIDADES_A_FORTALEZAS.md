# Plan de Conversión: Debilidades a Fortalezas

**Documento complementario al Análisis DOFA (Julio 2026)**
**Producto:** Orderfox / Velzia — Plataforma SaaS de gestión de pedidos para restaurantes

---

El análisis DOFA identificó 7 debilidades internas. Este plan propone acciones concretas para convertir cada una en una fortaleza medible.

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  1. Pocas pruebas automatizadas                     🔴 Prioridad | ✅ Completado ║
║                                                                             ║
║  → Implementar GitHub Actions que ejecute pruebas con cada cambio.          ║
║  → Exigir cobertura ≥ 80% en todo código nuevo.                             ║
║                                                                             ║
║  ✅ Éxito: Sin errores en producción después de lanzamientos.               ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║  2. Código desorganizado (lógica mezclada con presentación) 🔴 Prioridad | ✅ Completado ║
║                                                                             ║
║  → Separar lógica de negocio en capas de servicio (como ya existe en        ║
║    order_service.py). La presentación solo muestra datos, no los calcula.   ║
║                                                                             ║
║  ✅ Éxito: Nuevas funciones se agregan más rápido y con menos errores.      ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║  3. Duplicación auth web vs móvil               🟡 Prioridad | ✅ Completado ║
║                                                                             ║
║  → Unificar validación de acceso en un solo middleware que usen             ║
║    tanto la web como la API.                                                ║
║                                                                             ║
║  ✅ Éxito: Comportamiento idéntico en web y móvil.                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║  4. Sin pruebas de seguridad                   🔴 Prioridad | ✅ Completado ║
║                                                                             ║
║  → Auditoría automatizada cada 3 meses con OWASP ZAP.                       ║
║  → Revisión manual de puntos críticos (pagos, autenticación).               ║
║                                                                             ║
║  ✅ Éxito: Cero vulnerabilidades críticas. Clientes confían en sus datos.   ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║  5. Manejo de errores mejorable                🟡 Prioridad | ✅ Completado ║
║                                                                             ║
║  → Implementar logging con niveles y contexto (qué usuario, qué acción).    ║
║  → Agregar Sentry para capturar errores en producción automáticamente.     ║
║                                                                             ║
║  ✅ Éxito: Errores diagnosticados en minutos en lugar de horas.             ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║  6. Rendimiento móvil mejorable          🟡 Prioridad | ✅ Completado ║
║                                                                             ║
║  → Ajustar la consulta del menú para que cargue todo en una sola llamada,  ║
║    igual que ya funciona en la versión web.                                 ║
║                                                                             ║
║  ✅ Éxito: Tiempo de carga reducido a la mitad en celular.                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║  7. Clave de seguridad con respaldo fijo       🔴 Prioridad | ✅ Completado ║
║                                                                             ║
║  → Eliminar el valor hardcodeado. La app no arranca en producción           ║
║    si no hay una clave segura configurada en el .env.                       ║
║                                                                             ║
║  ✅ Éxito: Riesgo de seguridad eliminado por completo.                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## Resumen del plan

Tres debilidades son prioridad alta porque representan riesgos directos para el negocio:

| Prioridad | Debilidades | Estado |
|-----------|-------------|--------|
| 🔴 Alta | Pruebas, Código desorganizado, Clave hardcodeada + Seguridad | ✅ Completado |
| 🟡 Media | Auth duplicada, Errores, Rendimiento móvil | ✅ Completado |

**Cronograma ejecutado:**

| Periodo | Acciones | Estado |
|---------|----------|--------|
| **Mes 1** | Pruebas automatizadas + eliminar clave hardcodeada | ✅ Completado |
| **Mes 2** | Refactor de código por capas + unificar autenticación | ✅ Completado |
| **Mes 3** | Manejo de errores (Sentry) + rendimiento móvil + auditoría de seguridad | ✅ Completado |
