# PROC-05: Estrategia de Testing y QA

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Stack de Testing

| Herramienta | Propósito |
|-------------|-----------|
| **pytest** | Framework de pruebas unitarias y de integración |
| **pytest-flask** | Fixtures y contexto de aplicación Flask |
| **SQLAlchemy** | Base de datos de prueba (SQLite en memoria) |

---

## 2. Estructura de Tests

```
tests/
├── conftest.py               # Fixtures compartidos
├── test_subscription.py      # Pruebas de suscripción y planes
├── test_rate_limiter.py      # Pruebas de rate limiting
└── test_image_handler.py     # Pruebas de manejo de imágenes
```

---

## 3. Pirámide de Testing

```
        ╱╲
       ╱ E2E ╲           ← No implementado (faltan tests de interfaz)
      ╱────────╲
     ╱ Integración ╲      ← Tests de servicios + BD real
    ╱────────────────╲
   ╱   Unitarios       ╲   ← Tests de utilidades y funciones puras
  ╱──────────────────────╲
```

### Estado Actual

| Nivel | Cobertura | Prioridad |
|-------|-----------|-----------|
| **Unitarios** | ✅ Subscription utils, rate limiter | Mantener |
| **Integración** | ⚠️ Services tienen fixtures pero faltan tests | Alta |
| **API (REST)** | ❌ No existen tests de endpoints | Alta |
| **Frontend** | ❌ No existen tests JS | Media |
| **E2E** | ❌ No existen tests de navegador | Baja |

---

## 4. Cómo Ejecutar Tests

```bash
# Ejecutar todos los tests
pytest

# Ejecutar con verbose
pytest -v

# Ejecutar tests específicos
pytest tests/test_subscription.py -v

# Ejecutar por clase
pytest tests/test_subscription.py::TestIsSubscriptionActive -v

# Ejecutar con cobertura (si pytest-cov instalado)
pytest --cov=app tests/
```

---

## 5. Configuración reproducible de la suite

La suite no llama a Clerk ni a servicios externos. `tests/conftest.py` define
credenciales ficticias para atravesar los caminos que verifican la configuración:

```bash
SECRET_KEY=test-secret-key-for-testing-only
JWT_SECRET_KEY=test-secret-key-for-testing-only
CLERK_SECRET_KEY=sk_test_dummy
CLERK_PUBLISHABLE_KEY=pk_test_dummy
DATABASE_URL=sqlite:///:memory:
```

`CLERK_SECRET_KEY` es obligatoria para las pruebas de eliminación de cuenta,
pero su valor es únicamente un dummy y nunca debe ser una credencial real.
Los tests de telemetría de Copilot simulan DeepSeek y desactivan la búsqueda web
para no depender de `TAVILY_API_KEY`, internet ni un proveedor externo.

## 6. Fixtures Disponibles

Definidos en `tests/conftest.py`:

| Fixture | Descripción |
|---------|-------------|
| `app` | Instancia de aplicación Flask (modo testing) |
| `db` | Base de datos SQLite en memoria |
| `sample_restaurant` | Restaurante con suscripción activa |
| `expired_restaurant` | Restaurante con suscripción vencida |
| `grace_period_restaurant` | Restaurante en período de gracia |
| `trial_restaurant` | Restaurante en período de prueba |
| `sample_user` | Usuario asociado al restaurante |
| `sample_order` | Pedido de ejemplo asociado |

---

## 7. Convenciones para Escribir Tests

### Nomenclatura
```python
class TestNombreDelComponente:
    
    def test_escenario_descripcion(self, fixture):
        """Docstring opcional."""
        ...
```

### Patrón AAA (Arrange-Act-Assert)
```python
def test_calcula_descuento_correctamente(self):
    # Arrange
    precio = 10000
    descuento = 0.1
    
    # Act
    resultado = calcular_precio_con_descuento(precio, descuento)
    
    # Assert
    assert resultado == 9000
```

### Reglas
- Un test por escenario
- No depender del orden de ejecución
- Usar fixtures, no hacer setup manual en métodos de test
- Nombres descriptivos en español o inglés (consistente con el archivo)
- No usar `print()` en tests — usar `assert`

---

## 8. Checklist de QA Manual

Antes de cada release:

- [ ] `pytest` pasa sin errores
- [ ] `python run.py` inicia sin errores
- [ ] `npm run build:css` compila sin errores
- [ ] Login tradicional funciona
- [ ] Login con Clerk funciona
- [ ] Creación de producto funciona
- [ ] Creación de pedido funciona
- [ ] Menú público carga correctamente
- [ ] QR de mesa genera URL correcta
- [ ] Página de error 404 se muestra para rutas inválidas
- [ ] Página de error 500 se muestra para errores internos
- [ ] Suscripción activa permite CRUD
- [ ] Grace period bloquea CRUD
- [ ] Rate limiting bloquea pedidos rápidos

---

## 9. Plan de Mejora

| Corto Plazo (1-2 semanas) | Mediano Plazo (1 mes) | Largo Plazo (3 meses) |
|--------------------------|----------------------|----------------------|
| Tests de endpoints API | Tests de frontend JS | Tests E2E (Playwright) |
| CI/CD con pytest en GitHub Actions | Cobertura >70% | Visual regression tests |
| Tests de servicios faltantes | Tests de integración con Clerk mock | Performance/Load tests |

---

## 10. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
