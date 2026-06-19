# Documentación de Orderfox

**Versión del proyecto:** 1.3.0 | **Última actualización:** 2026-06-16

Mapa de navegación de toda la documentación técnica del proyecto.

---

## 00-GOVERNANCE — Políticas y Gobernanza

Documentos normativos de alto nivel.

| Documento | Descripción |
|-----------|-------------|
| [POL-01: Código de Conducto](00-GOVERNANCE/POL-01_Codigo_de_Conducto.md) | Normas éticas, profesionales y colaborativas del equipo |
| [POL-02: Política de Seguridad](00-GOVERNANCE/POL-02_Politica_de_Seguridad.md) | Normas de seguridad, reporte de vulnerabilidades y prácticas seguras |

---

## 01-ARCHITECTURE — Arquitectura del Sistema

Documentos de diseño y visión general.

| Documento | Descripción |
|-----------|-------------|
| [ARCH-01: Visión General](01-ARCHITECTURE/ARCH-01_Visión_General.md) | Arquitectura del proyecto, componentes y flujos principales |
| [ARCH-02: Diagrama ERD](01-ARCHITECTURE/ARCH-02_Diagrama_ERD.md) | Esquema de base de datos, tablas y relaciones |
| [ARCH-03: Autenticación](01-ARCHITECTURE/ARCH-03_Autenticacion.md) | Política de autenticación y flujo de creación de usuarios |
| [ARCH-04: Flujo de Suscripción](01-ARCHITECTURE/ARCH-04_Flujo_de_Suscripcion.md) | Ciclo de vida de suscripciones, trials y facturación |

---

## 02-GUIDES — Guías Técnicas

Documentos de implementación y referencia.

| Documento | Descripción |
|-----------|-------------|
| [GUIDE-01: Timezone Handling](02-GUIDES/GUIDE-01_Timezone_Handling.md) | Manejo de fechas UTC y estados de suscripción |
| [GUIDE-02: Rate Limiting](02-GUIDES/GUIDE-02_Rate_Limiting.md) | Sistema inteligente de rate limiting para pedidos |
| [GUIDE-03: API Reference](02-GUIDES/GUIDE-03_API_Reference.md) | Documentación completa de endpoints REST |
| [GUIDE-04: Scanner IA](02-GUIDES/GUIDE-04_Integracion_ScannerIA.md) | Integración con el servicio externo de inteligencia artificial |
| [GUIDE-05: Estrategia PWA](02-GUIDES/GUIDE-05_Estrategia_Offline_PWA.md) | Estrategia offline, carrito y service workers |
| [GUIDE-06: Env Vars](02-GUIDES/GUIDE-06_Referencia_Env_Vars.md) | Referencia completa de variables de entorno |

---

## 03-PROCEDURES — Procedimientos Operativos

Runbooks y procesos paso a paso.

| Documento | Descripción |
|-----------|-------------|
| [PROC-01: Deployment Runbook](03-PROCEDURES/PROC-01_Deployment_Runbook.md) | Despliegue a producción, configuración y rollback |
| [PROC-02: Incident Response](03-PROCEDURES/PROC-02_Incident_Response.md) | Plan de respuesta a incidentes y post-mortem |
| [PROC-04: Onboarding Dev](03-PROCEDURES/PROC-04_Onboarding_Dev.md) | Guía de onboarding para nuevos desarrolladores |
| [PROC-05: Testing y QA](03-PROCEDURES/PROC-05_Testing_QA.md) | Estrategia de testing, fixtures y checklist de QA |

---

## 04-RECORDS — Registros Históricos

Bitácoras y planes de prueba.

| Documento | Descripción |
|-----------|-------------|
| [CHANGELOG](../CHANGELOG.md) | Historial de versiones del proyecto |
| [REC-02: Decision Log](04-RECORDS/REC-02_Decision_Log.md) | Registro de decisiones técnicas (ADRs) |
| [Test Plan: Login](04-RECORDS/Test_Plans/TEST_PLAN_LOGIN.md) | Plan de prueba para recuperación de login |

---

## Referencias Cruzadas

- [AGENTS.md](../AGENTS.md) — Guía rápida para agentes AI y desarrolladores
- [README.md](../README.md) — Landing page del repositorio
- [settings.py](../settings.py) — Configuración de variables de entorno
- [.opencode/agents/](../.opencode/agents/) — Configuración de agentes AI
- [.github/](../.github/) — CI/CD workflows y templates de issues/PR
