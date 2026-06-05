# Análisis de Calidad de Código y Plan de Refactorización — Orderfox/Velzia

> **Versión del análisis:** 1.0  
> **Fecha:** 2026-06-03  
> **Alcance:** Backend Python/Flask + MySQL  
> **Audiencia:** Equipo de desarrollo  
> **Plazo estimado:** 2-4 semanas (18-20 días hábiles)

---

## Resumen Ejecutivo

| Métrica | Hallazgo |
|---------|----------|
| Archivos backend | 33 `.py` (~298 KB) |
| Duplicación crítica | **Dos APIs paralelas** (session + JWT) con ~70% lógica duplicada |
| Tests Python | **0** (cero) — solo 3 tests E2E en Playwright |
| Líneas por archivo | `auth.py`: 761, `api_auth.py`: 639, `orders.py`: 285, `api_orders.py`: 426 |
| Blueprints totales | **18 blueprints** registrados en `create_app()` |
| Ratio ruteo/servicio | **~95% rutas, ~5% lógica de negocio separada** |

---

## 🔴 P1 — Duplicación Masiva: Sistema de Rutas Dual (Session + JWT)

### Problema

Existen **dos capas de API completamente paralelas** con lógica de negocio duplicada:

- **Web (session)**: `routes/auth.py`, `routes/orders.py`, `routes/products.py`, `routes/categories.py`, etc.
- **Mobile (JWT)**: `routes/api_auth.py`, `routes/api_orders.py`, `routes/api_products.py`, `routes/api_categories.py`, etc.

Cada funcionalidad se implementa dos veces. Comparemos `generate_order_number()`:

**`routes/orders.py:12`**:
```python
def generate_order_number(restaurant_id):
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    count = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.created_at >= today_start
    ).count()
    return f"ORD-{count + 1:03d}"
```

**`routes/api_orders.py:12`**:
```python
def generate_order_number(restaurant_id):
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    count = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.created_at >= today_start
    ).count()
    return f"ORD-{count + 1:03d}"
```

Idénticas. Lo mismo ocurre con `validate_status_transition()`, `send_otp_email()`, `RESERVED_SLUGS`, y el mapeo de planes. **El webhook de Mercado Pago (`auth.py:659`) ni siquiera tiene versión API.**

### Causa Raíz

El sistema evolucionó agregando una API móvil (JWT) sin refactorizar la existente (session). En lugar de extraer la lógica de negocio a un **service layer** compartido, se copió/pegó todo el archivo.

### Propuesta de Refactorización

**Extraer un Service Layer unificado:**

```python
# services/order_service.py
class OrderService:
    @staticmethod
    def generate_order_number(restaurant_id):
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        count = Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.created_at >= today_start
        ).count()
        return f"ORD-{count + 1:03d}"

    @staticmethod
    def validate_status_transition(current, new):
        valid = {
            'pending': ['confirmed', 'cancelled', 'expired'],
            'confirmed': ['delivered', 'cancelled'],
            'delivered': [],
            'cancelled': ['pending'],
            'expired': []
        }
        return new in valid.get(current, [])
```

Luego simplificar **ambas** rutas para que solo orquesten request/response:

```python
# routes/orders.py
@orders_bp.route('/<int:id>/status', methods=['PATCH'])
@login_required
def change_status(id):
    restaurant = get_current_restaurant()
    if not check_feature_access(restaurant, 'has_status_management'):
        return jsonify({'error': 'Plan insuficiente'}), 403

    data = request.get_json()
    if not OrderService.validate_status_transition(order.status, data['status']):
        return jsonify({'error': 'Transición inválida'}), 400

    order.status = data['status']
    db.session.commit()
    return jsonify({'success': True})
```

```python
# routes/api_orders.py
@api_orders_bp.route('/<int:id>/status', methods=['PATCH'])
@jwt_login_required
def change_status(id):
    # MISMAS 5 líneas de lógica REAL — solo cambia el decorador de auth
    restaurant = get_current_restaurant_jwt()
    # ... exactamente el mismo código del service
```

### Beneficios

- Elimina ~3,000+ líneas duplicadas
- Cambios de lógica de negocio se hacen en UN solo lugar
- Mejora drásticamente el testing (tests unitarios contra services)
- Reduce riesgo de bugs asimétricos (web vs API comportándose distinto)

### Riesgos

- Refactorización de alto riesgo si no hay tests de regresión (y no los hay)
- Requiere mapear exhaustivamente todos los endpoints antes de mover lógica
- Los formatos de respuesta (HTML vs JSON) deben mantenerse separados

### Esfuerzo

**3-5 días** para mapear, extraer services principales (OrderService, ProductService, AuthService, CategoryService) y migrar las rutas.

---

## 🔴 P2 — Violación SRP: Fat Routes con Lógica de Negocio Incrustada

### Problema

Las "rutas" (controllers) contienen lógica de negocio, manejo de sesión, validaciones de suscripción, cálculos de fechas y transacciones de base de datos. Ejemplo en `public.py:89-249` (`create_order`):

```python
@public_bp.route('/menu/api/order', methods=['POST'])
def create_order():
    # Anti-bot honeypot validation
    # Time-to-submit validation
    # Restaurant lookup
    # Subscription check
    # Expire old orders
    # Rate limiting
    # Generate order number
    # Build notes with table/address info
    # Create Order + flush
    # Iterate cart items
    # Validate each product in DB
    # Validate each modifier in DB
    # Calculate subtotals
    # Create OrderItems
    # Commit
    # Return response
```

**161 líneas** de lógica mezclada. Similar: `auth.py:27-171` (`sync_clerk`) — 144 líneas que mezclan verificación Clerk, creación de usuario, wallet de tokens, manejo de sesión y respuesta.

### Causa Raíz

No hubo separación arquitectónica desde el inicio. Flask no impone una estructura — se empezó con prototipos rápidos y se acumuló lógica en los blueprints.

### Propuesta de Refactorización

Aplicar **Arquitectura en Capas**:

```
routes/           → Solo HTTP (request parsing, response formatting, auth decorators)
services/         → Lógica de negocio pura (sin request/response)
repositories/     → Queries a DB (abstracting SQLAlchemy)
```

Ejemplo:

```python
# services/order_service.py
class OrderCreationService:
    def __init__(self, anti_bot=None, rate_limiter=None):
        self.anti_bot = anti_bot or OrderAntiBot()
        self.rate_limiter = rate_limiter or OrderRateLimiter()

    def create_order(self, restaurant_id, cart_data, customer_info, ip_address):
        self.anti_bot.validate(cart_data)
        self.rate_limiter.check(restaurant_id, ip_address)

        order = Order(restaurant_id=restaurant_id, ...)
        for item in cart_data:
            product = ProductRepository.get_active(item['product_id'])
            # ... business logic
        return order
```

### Esfuerzo

**2-3 semanas** para migrar los 18 blueprints. Priorizar: `public.py` (creación de orden), `auth.py` (registro/flujo Clerk).

---

## 🔴 P3 — Ausencia Total de Tests (Auto-Contradicción en requirements)

### Problema

**Cero tests de Python.** `requirements.txt` incluye `pytest` y `pytest-cov`, pero no hay un solo archivo `test_*.py`. El único test es `tests/example.spec.js` (Playwright) con 3 tests de login.

Esto significa:
- **Cualquier refactorización es a ciegas** — no hay safety net
- Errores de regresión son inevitables
- La calidad es completamente reactiva (bugs aparecen en producción)

### Causa Raíz

Cultura de "ship fast" sin inversión en testing. Proyecto comenzó como MVP y nunca se estableció disciplina de testing.

### Propuesta de Refactorización

**Estrategia de testing por capas:**

1. **Unit tests (semana 1):** Testear los servicios más críticos
   - `OrderService.generate_order_number()` — secuencialidad, reinicio diario
   - `subscription.is_subscription_active()` — casos borde UTC, grace period
   - `subscription.get_subscription_status()` — 6 estados con fechas simuladas

2. **Integration tests (semana 2):** Testear endpoints críticos con DB real (SQLite en memoria)
   - Flujo completo de creación de orden pública
   - Webhook de Mercado Pago
   - Login y autenticación

3. **Propuesta de fixture:**

```python
# tests/conftest.py
@pytest.fixture
def app():
    app = create_app()
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app

@pytest.fixture
def restaurant(app):
    r = Restaurant(name='Test', slug='test', ...)
    db.session.add(r)
    db.session.commit()
    return r
```

### Esfuerzo

**3-5 días** para establecer infraestructura de testing (conftest, fixtures, factories) y tests críticos. El costo de NO hacerlo es exponencialmente mayor durante la refactorización.

---

## 🟠 P4 — Fragilidad en el Rate Limiter (Anti-Bot)

### Problema en `utils/rate_limiter.py:16-24`

```python
@staticmethod
def get_recent_orders_count(restaurant_id, client_ip, minutes=1):
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.notes.ilike(f"%IP:{client_ip}%"),
        ...
    ).count()
```

**El rate limiter busca la IP del cliente dentro del campo `notes`** usando `ILike` — esto es:
- **Ineficiente**: escaneo de texto, no hay índice
- **No confiable**: si alguien edita notas desde el dashboard, se pierde el tracking
- **Falso negativo**: si el campo `notes` se usa para otros propósitos y se sobrescribe

### Causa Raíz

No hay un campo dedicado `ip_address` en el modelo `Order`. Se improvisó guardando la IP en las notas como un side-effect.

### Propuesta

```python
# models.py
class Order(db.Model):
    __tablename__ = 'orders'
    id = ...
    ip_address = db.Column(db.String(45), nullable=True, index=True)  # IPv6 soporta hasta 45 chars

# rate_limiter.py
@staticmethod
def get_recent_orders_count(restaurant_id, client_ip, minutes=1):
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.ip_address == client_ip,
        Order.created_at >= since,
        Order.status.in_(['pending', 'confirmed'])
    ).count()
```

### Esfuerzo

**1 día** — migración del modelo + actualización del rate limiter + script de backfill para datos existentes.

---

## 🟠 P5 — Race Condition en Generación de Número de Orden

### Problema en `routes/public.py:23-25` y `routes/orders.py:12-22`

```python
def generate_order_number(restaurant_id):
    count = Order.query.filter_by(restaurant_id=restaurant_id).count()
    return f"ORD-{count + 1:03d}"
```

**Versión pública (`public.py:23-25`)** usa `count()` sin filtro de fecha — si dos pedidos llegan simultáneamente, ambos obtienen el mismo número.

**Versión web (`orders.py:12-22`)** usa filtro diario, pero igual sin bloqueo — dos pedidos paralelos en el mismo día colisionan.

### Causa Raíz

No se usa una secuencia de base de datos ni un lock pesimista. La generación del número de orden no es atómica.

### Propuesta

**Opción A (recomendada):** Usar `SELECT ... FOR UPDATE` (lock pesimista) o un contador atómico:

```python
# Usar SQL sequence o tabla separada order_counters
class OrderCounter(db.Model):
    __tablename__ = 'order_counters'
    restaurant_id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, primary_key=True)
    counter = db.Column(db.Integer, default=0)

def generate_order_number(restaurant_id):
    today = date.today()
    counter = OrderCounter.query.with_for_update().filter_by(
        restaurant_id=restaurant_id, date=today
    ).first()
    if not counter:
        counter = OrderCounter(restaurant_id=restaurant_id, date=today, counter=1)
        db.session.add(counter)
    else:
        counter.counter += 1
    db.session.commit()
    return f"ORD-{counter.counter:03d}"
```

**Opción B:** Migrar a UUIDs como identificador único + número secuencial decorativo (no único).

### Esfuerzo

**1-2 días** — migración de modelo + contador atómico.

---

## 🟠 P6 — Seguridad: JWT Token en URL (Severidad Media-Alta)

### Problema en `routes/api_dashboard.py:409-414`

```python
signed_token = pyjwt.encode(...)
return jsonify({
    'success': True,
    'data': {
        'token': signed_token,
        'scanner_url': f'{scanner_url}/flask-auth?flask_token={signed_token}'  # ← TOKEN EN URL
    }
})
```

Los JWT tokens en URLs:
- Quedan en logs del servidor (accesibles a admins)
- Quedan en historial del navegador
- Se exponen en el `Referer` header a otros sitios
- No pueden ser revocados (no hay blacklist)

### Causa Raíz

El scanner IA (Next.js/Node) necesita autenticarse contra Flask, y se eligió la vía más simple: token por query param.

### Propuesta

Usar **POST con Header** o **signed cookies**:

```python
return jsonify({
    'success': True,
    'data': {
        'token': signed_token,
        'method': 'Authorization: Bearer <token>',
        'scanner_url': f'{scanner_url}/flask-auth'
    }
})
```

### Esfuerzo

**Medio día** — cambiar token de URL a header en ambos lados (Flask + Scanner IA).

---

## 🟡 P7 — Manejo Inconsistente de Timezone en Tareas Programadas

### Problema en `tasks.py:20,64`

```python
# _perform_cleanup():
cutoff_time = datetime.now() - timedelta(hours=24)  # ← naive datetime

# _perform_expiry():
now = datetime.now()  # ← naive datetime

# _perform_reminders():
now = datetime.now(timezone.utc)  # ← aware datetime ✓
```

**Tres funciones, tres estrategias de timezone.** Puede causar:
- Borrado de restaurantes inactivos en el momento equivocado del día
- Expiración de órdenes fuera de la ventana esperada

### Causa Raíz

El `AwareDateTime` custom type de los modelos creó confusión. Las tareas bypassan el TypeDecorator al usar datetime de Python directamente.

### Propuesta

Unificar todas las tareas para usar `datetime.now(timezone.utc)` consistentemente.

### Esfuerzo

**2-4 horas**

---

## 🟡 P8 — Fragilidad en Manejo de Errores

### Problemas identificados:

**1. Bare excepts que ocultan errores (`app/__init__.py:161-162`):**
```python
try:
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
except Exception as e:
    pass  # ← Traga TODAS las excepciones silenciosamente
```

**2. Bloques `try/except/pass` en webhook (`auth.py:746-747`):**
```python
try:
    sanitize_restaurant_limits(restaurant)
    ...
except Exception as e:
    pass  # ← Si falla el wallet reset, no se loguea
```

### Propuesta

```python
try:
    ...
except Exception as e:
    current_app.logger.error(f"Error en webhook process: {e}", exc_info=True)
    db.session.rollback()
    raise
```

### Esfuerzo

**1-2 días** — auditoría de todos los manejos de error + reemplazar pass con logging + cleanup.

---

## 🟡 P9 — N+1 Query Problem en Menú Público

### Problema en `routes/public.py:61-76`

```python
categories = Category.query.filter_by(
    restaurant_id=restaurant.id, is_active=True
).order_by(Category.sort_order).all()

# N+1: por cada categoría, se hace una query adicional
for cat in categories:
    cat.products = Product.query.filter_by(
        category_id=cat.id, restaurant_id=restaurant.id, is_active=True
    ).all()
    cat.active_product_count = len(cat.products)
```

Si un restaurante tiene 20 categorías → **1 query de categorías + 20 queries de productos = 21 queries**.

### Propuesta

```python
from sqlalchemy.orm import joinedload

categories = Category.query.options(
    joinedload(Category.products)
).filter(
    Category.restaurant_id == restaurant.id,
    Category.is_active == True
).order_by(Category.sort_order).all()

# Filtrar productos activos en memoria
for cat in categories:
    cat.products = [p for p in cat.products if p.is_active]
    cat.active_product_count = len(cat.products)
```

### Esfuerzo

**4 horas**

---

## 🟡 P10 — CSRF Inconsistente

### Problema

Hay un sistema de CSRF custom que se salta el default de Flask-WTF:

```python
# app/__init__.py:92-94
@app.before_request
def check_csrf_for_non_api():
    if not request.path.startswith('/api/') and request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
        csrf.protect()
```

La configuración `WTF_CSRF_CHECK_DEFAULT = False` deshabilita la protección automática de Flask-WTF, delegando al `before_request` manual. Esto es frágil porque:
- Si se agrega un nuevo blueprint, hay que acordarse del CSRF
- No hay tests que verifiquen qué endpoints están protegidos

### Propuesta

Usar el sistema nativo de Flask-WTF (`WTF_CSRF_CHECK_DEFAULT = True`) y marcar explícitamente los endpoints API como `@csrf.exempt`. Eliminar el `before_request` custom.

### Esfuerzo

**1 día** — cambios en config + añadir/remover decoradores.

---

## 🟡 P11 — Duplicación de Configuración de Planes

### Problema

La configuración de planes está definida en **3 lugares diferentes**:

1. `utils/subscription.py:4-41` → `PLAN_LIMITS` dict
2. `routes/auth.py:550-557` → `plans_data` dict (precios duplicados)
3. `routes/api_auth.py:442-505` → `plans_config` (re-definición completa)

### Causa Raíz

La configuración de planes se fue agregando incrementalmente sin consolidación.

### Propuesta

Unificar TODO en `utils/subscription.py`:

```python
PLAN_LIMITS = {
    'emprendedor': {
        'max_products': 25, 'has_qr': True, 'has_modifiers': False,
        'price_cop': 30000, 'name': 'Emprendedor', 'duration_days': 30,
    },
    ...
}
```

### Esfuerzo

**4 horas**

---

## 🟡 P12 — Imports dentro de funciones (Lazy Imports)

### Problemas generalizados

En prácticamente todos los archivos hay imports dentro de funciones, lo que:
- Oculta dependencias reales del módulo
- Dificulta el análisis estático (linters, type checkers)
- Oculta errores de import hasta runtime

### Causa Raíz

Circular imports no resueltos adecuadamente. Se usó lazy import como muleta.

### Propuesta

Reestructurar el punto de entrada para que `models.py` sea independiente (separar `db` de los modelos de dominio), y mover los imports al tope.

### Esfuerzo

**2-3 días** — requiere reestructurar el `create_app()` y romper dependencias circulares.

---

## 🟢 P13 — Token Elite: `3000` hardcodeado como "infinito"

### Problema en `models.py:273-274`

```python
@property
def total_available(self):
    if self.is_elite:
        return 3000  # Simulado como ilimitado
```

Si un usuario Elite consume 3000 tokens en un mes, el sistema dirá que no le quedan tokens.

### Propuesta

```python
@property
def total_available(self):
    if self.is_elite:
        return float('inf')
    return self.plan_tokens + self.extra_tokens

def can_scan(self):
    return self.is_elite or self.total_available > 0
```

### Esfuerzo

**30 minutos**

---

## 🟢 P14 — Config expuesta como string en producción

### Problema en `settings.py:13`

```python
SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-clave-secreta-muy-larga-para-desarrollo-seguro'
```

Si en producción no se configura `SECRET_KEY`, se usa el fallback hardcodeado.

### Propuesta

```python
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in production")
```

### Esfuerzo

**10 minutos**

---

## 🟢 P15 — CORS totalmente abierto

### Problema en `app/__init__.py:38`

```python
CORS(app, resources={r"/api/*": {"origins": "*"}})
```

CORS con `origins: "*"` en `/api/*` permite que cualquier sitio web haga peticiones desde el navegador del usuario autenticado.

### Propuesta

```python
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://velzia.co",
            "https://admin.velzia.co",
            app.config.get('SCANNER_IA_URL', ''),
        ],
        "supports_credentials": True
    }
})
```

### Esfuerzo

**30 minutos**

---

## 🟢 P16 — Duplicación del RESERVED_SLUGS

Definido en `auth.py:21-25` y `api_auth.py:19-23`. Idéntico. Debería estar en `utils/subscription.py` o un `constants.py`.

---

## Matriz de Priorización

| ID | Problema | Impacto | Esfuerzo | Prioridad |
|----|----------|---------|----------|-----------|
| P1 | Duplicación masiva rutas web/API | 🔴 Alto | 3-5 días | **CRÍTICO** |
| P2 | Fat routes sin SRP | 🔴 Alto | 2-3 sem | **CRÍTICO** |
| P3 | Cero tests Python | 🔴 Alto | 3-5 días | **CRÍTICO** |
| P4 | Rate limiter frágil | 🟠 Medio | 1 día | **ALTA** |
| P5 | Race condition order number | 🟠 Medio | 1-2 días | **ALTA** |
| P6 | JWT en URL | 🟠 Medio | 0.5 día | **ALTA** |
| P7 | Timezone inconsistente | 🟡 Bajo | 2-4 h | **MEDIA** |
| P8 | Error handling frágil | 🟡 Bajo | 1-2 días | **MEDIA** |
| P9 | N+1 queries menú | 🟡 Bajo | 4 h | **MEDIA** |
| P10 | CSRF inconsistente | 🟡 Bajo | 1 día | **MEDIA** |
| P11 | Config planes duplicada | 🟡 Bajo | 4 h | **MEDIA** |
| P12 | Lazy imports | 🟡 Bajo | 2-3 días | **BAJA** |
| P13 | Tokens Elite falsos | 🟢 Muy Bajo | 30 min | **BAJA** |
| P14 | Secret key fallback | 🟢 Muy Bajo | 10 min | **BAJA** |
| P15 | CORS abierto | 🟢 Muy Bajo | 30 min | **BAJA** |
| P16 | Slug duplicado | 🟢 Muy Bajo | 10 min | **BAJA** |

---

## Plan de Acción Recomendado (2-4 semanas)

### Sprint 1 (Semana 1-2): Fundaciones

| Día | Actividad |
|-----|-----------|
| 1-3 | **P3**: Setup de testing (pytest, conftest, fixtures, CI) |
| 2-4 | **P1**: Extraer `services/order_service.py`, `services/product_service.py`, `services/auth_service.py` |
| 3-5 | **P1**: Refactorizar 4 pares de rutas (orders + api_orders, products + api_products) |

### Sprint 2 (Semana 2-4): Refactorización y Correcciones

| Día | Actividad |
|-----|-----------|
| 1-2 | **P5**: Order counter atómico + **P4**: ip_address field |
| 2-3 | **P11**: Unificar PLAN_LIMITS |
| 3-4 | **P9**: Eager loading menú público + **P10**: CSRF nativo |
| 4-5 | **P6**: JWT token out of URL + **P15**: CORS restrictivo |
| 5-7 | **P12**: Eliminar lazy imports |
| 7-8 | **P7, P8, P13**: Correcciones menores + **P14**: Validación SECRET_KEY |
| 8-10 | **P2**: Migrar rutas restantes a servicios |

---

## Próximos Pasos

1. ✅ Revisar este plan con el equipo
2. ⬜ Priorizar los items según necesidades del negocio
3. ⬜ Decidir sprint 1 vs sprint 2
4. ⬜ Establecer primeras tareas asignadas

---

*Documento generado a partir del análisis estático del código fuente en `app/`, `routes/`, `utils/`, `models.py`, `tasks.py`, `settings.py`.*
