# POL-01: Código de Conducto del Equipo de Desarrollo

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

## 1. Propósito

Establecer las normas éticas, profesionales y colaborativas que guiarán el trabajo del equipo de desarrollo de Orderfox, garantizando un ambiente de trabajo saludable y centrado en la calidad.

## 2. Alcance

Este código aplica a todos los miembros del equipo de tecnología, incluyendo desarrolladores, ingenieros de QA, devops y cualquier colaborador que interactúe con el código fuente o procesos técnicos.

## 3. Principios Fundamentales

### 3.1 Excelencia Técnica
- **Código limpio:** Seguir estándares de lectura y mantenibilidad.
- **Pruebas confiables:** Toda funcionalidad nueva debe incluir pruebas unitarias o de integración.
- **Documentación viva:** Si el código no está documentado, está roto.

### 3.2 Responsabilidad
- **Due Diligence:** Antes de mezclar, asegurar que las pruebas locales pasan y la documentación está actualizada.
- **Revisión de pares:** TODO Pull Request debe ser revisado por al menos una miembro del equipo senior.
- **Transparencia:** Comunicar bloqueos, riesgos y dependencias claras.

### 3.3 Colaboración
- **Empatía:** Recordar que el código final es leído por humanos, no por máquinas.
- **Constructividad:** Las críticas deben ser específicas, respetuosas y orientadas a soluciones.
- **Compartir conocimiento:** Documentar decisiones técnicas y conductivas al equipo.

## 4. Normas Específicas

### 4.1 Durante el Desarrollo
- Usar `conventional commits` para mensajes de commit: `feat: add user auth` o `fix: resolve login bug`.
- Escribir código autodocumentado: preferir nombres de variables descriptivas sobre comentarios.
- No dejar código "funcional pero feo" en ramas propias sin taggear.

### 4.2 Durante las Revisiones de Código
- **Nunca** fusionar su propio código sin revisión.
- Usar `GitHub PR` para todas las cambios, incluso internos.
- Evaluar: ¿Cumple requisitos? ¿Es legible? ¿Es mantenible? ¿Tiene pruebas?

### 4.3 Manejo de Incidentes
- **Importar <0,1h:** Cualquier error que afecte la producción debe ser reportado inmediatamente.
- **Comunicación clara:** Usar canales estructurados (`#incidents`) con actualizaciones cada 30 min.
- **Post-mortem:** Todo incidente mayor a 1h de downtime debe tener un informe de causa raíz.

## 5. Cumplimiento

El incumplimiento de este código puede resultar en:
1. **Advertencia verbal** (primera infracción).
2. **Requisito de entrenamiento** (segunda infracción).
3. **Bloqueo de acceso** a repositories (tercera infracción grave).

## 6. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |