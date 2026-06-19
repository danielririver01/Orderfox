# PROC-04: Guía de Onboarding para Desarrolladores

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Primer Día

### 1.1 Accesos necesarios

- [ ] Repositorio GitHub (acceso de lectura/escritura)
- [ ] Dashboard de Clerk (credenciales de prueba)
- [ ] Dashboard de Cloudinary (credenciales de prueba)
- [ ] Cuenta de Mercado Pago (modo sandbox)
- [ ] Acceso al servidor de pruebas (si aplica)
- [ ] Slack/WhatsApp del equipo

### 1.2 Lecturas obligatorias

- [ ] `README.md` — Visión general del proyecto
- [ ] `AGENTS.md` — Guía rápida de convenciones y gotchas
- [ ] `docs/README.md` — Mapa de documentación
- [ ] `docs/01-ARCHITECTURE/ARCH-01_Visión_General.md` — Arquitectura
- [ ] `docs/00-GOVERNANCE/POL-01_Codigo_de_Conducto.md` — Normas del equipo

### 1.3 Setup local (1-2 horas)

```bash
# 1. Clonar repositorio
git clone https://github.com/danielririver01/Orderfox.git
cd Orderfox

# 2. Activar entorno virtual (Windows)
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt
npm install

# 4. Copiar y configurar .env
cp .env.example .env
# Editar .env con credenciales de desarrollo

# 5. Crear base de datos MySQL
mysql -u root -p
CREATE DATABASE orderfox CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;

# 6. Ejecutar migraciones
flask db upgrade

# 7. Compilar CSS
npm run build:css

# 8. Iniciar servidor
python run.py
```

**Verificar:** Visitar http://localhost:5000 — debe cargar la página de login.

---

## 2. Flujo de Trabajo Diario

### 2.1 Ciclo de Desarrollo

```
1. git pull (obtener últimos cambios)
2. Crear rama: git checkout -b feat/nombre-cambio
3. Desarrollar + pruebas locales
4. git add + git commit (conventional commits)
5. git push + crear Pull Request
6. Solicitar revisión (al menos 1 reviewer)
7. Merge a main tras aprobación
```

### 2.2 Conventional Commits

| Prefix | Uso | Ejemplo |
|--------|-----|---------|
| `feat:` | Nueva funcionalidad | `feat: add dark mode toggle` |
| `fix:` | Corrección de bug | `fix: resolve login redirect loop` |
| `refactor:` | Refactorización | `refactor: extract order validation` |
| `docs:` | Documentación | `docs: update deployment runbook` |
| `test:` | Pruebas | `test: add order service unit tests` |
| `chore:` | Mantenimiento | `chore: update dependencies` |

### 2.3 Antes de Hacer Commit

- [ ] Pruebas locales pasan
- [ ] `python run.py` funciona sin errores
- [ ] `npm run build:css` compila sin errores
- [ ] Código sigue convenciones del proyecto (snake_case BD, camelCase JS)
- [ ] Documentación actualizada si aplica

---

## 3. Arquitectura para Nuevos Desarrolladores

### 3.1 Mapa de Archivos Clave

| Archivo | Qué hace | Cuándo tocarlo |
|---------|----------|----------------|
| `run.py` | Punto de entrada | Casi nunca |
| `settings.py` | Configuración | Agregar variable de entorno |
| `app/__init__.py` | App factory, blueprints, hooks | Agregar blueprint o middleware |
| `app/models.py` | Modelos de BD | Nueva tabla o columna |
| `app/extensions.py` | Extensiones Flask | Nueva extensión |
| `app/services/*.py` | Lógica de negocio | Nueva funcionalidad |
| `app/routes/*.py` | Rutas web | Nueva página |
| `app/routes/api_*.py` | Rutas API | Nuevo endpoint JSON |
| `app/static/js/*.js` | Frontend | Nueva interacción JS |
| `app/template/*.html` | Vistas HTML | Nueva página o componente |

### 3.2 Patrón para Agregar un Nuevo Endpoint

**Caso: Agregar endpoint de reportes**

```
1. Crear service: app/services/report_service.py
2. Crear ruta web: app/routes/reports.py (blueprint)
3. Crear ruta API: app/routes/api_reports.py (blueprint)
4. Registrar ambos blueprints en app/__init__.py
5. Crear template: app/template/dashboard/reports.html
6. Agregar JS: app/static/js/reports.js
7. Agregar a navegación: app/template/common/navigation.html
8. Si hay nuevo modelo: flask db migrate -m "add reports"
9. Documentar en docs/ si es funcionalidad compleja
```

---

## 4. Comandos Útiles

```bash
# Desarrollo
python run.py                                  # Servidor local
npm run watch:css                              # Tailwind en modo watch
flask db migrate -m "descripción"              # Crear migración
flask db upgrade                               # Aplicar migración

# Debug
python test_db.py                              # Verificar BD
python rescues_db.py                           # Rescatar datos
python test_subscription_utc.py                # Probar timezone

# Producción
npm run build:css                              # Compilar CSS producción
gunicorn --workers 4 run:app                   # Servir con Gunicorn
```

---

## 5. Glosario del Proyecto

| Término | Significado |
|---------|-------------|
| **Slug** | Identificador único en URL (ej: `mi-restaurante`) |
| **Plan type** | Tipo de suscripción: trial, emprendedor, crecimiento, elite |
| **Grace period** | 14 días post-expiración donde no se puede hacer CRUD |
| **Token AI** | Créditos para usar Scanner IA (1 escaneo = 1 token) |
| **Top-up** | Compra adicional de tokens vía Mercado Pago |
| **Scanner IA** | Servicio externo que consume tokens para análisis |
| **Clerk** | Proveedor OAuth (login social) |
| **AwareDateTime** | Decorador que maneja conversión UTC automática |
| **Honeypot** | Campo oculto en formularios para detectar bots |
| **Rate limiting** | Control de frecuencia de pedidos por IP |

---

## 6. Cómo Pedir Ayuda

1. **Bug o duda técnica** → Abrir GitHub Issue con etiqueta `question`
2. **Problema de producción** → Seguir PROC-02 (Incident Response)
3. **Duda de convenciones** → Leer `AGENTS.md` sección "Key Conventions"
4. **Problema de setup** → Revisar sección 1.3 de este documento
5. **Documentación faltante** → Crear PR con la mejora

---

## 7. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
