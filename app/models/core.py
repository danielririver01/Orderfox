"""
Modelos del núcleo: tipos base, Restaurant, User, catálogo de productos.
"""

from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import db


class AwareDateTime(db.TypeDecorator):
    """
    Asegura que los objetos datetime sean siempre UTC-aware al leer,
    y se guarden correctamente en UTC al escribir.
    """
    impl = db.DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """
        Al guardar en DB: Convierte aware a UTC naive (para MySQL)
        """
        if value is not None:
            if value.tzinfo is None:
                # Si es naive, asumimos que ya está en UTC
                return value
            else:
                # Si es aware, convertir a UTC y remover tzinfo
                return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        """
        Al leer de DB: Convierte naive a UTC aware
        """
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Restaurant(db.Model):
    __tablename__ = 'restaurants'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    whatsapp_phone = db.Column(db.String(20), nullable=False)
    # Rediseño menú público (v1.5): identidad visual y metadata del menú.
    cover_image = db.Column(db.String(255), nullable=True)      # URL propia (Cloudinary); null = banco por cuisine_type
    estimated_time = db.Column(db.Integer, nullable=True)        # Minutos de preparación; null = ocultar en UI
    brand_color = db.Column(db.String(7), nullable=True)         # Hex '#RRGGBB'; null = acento por defecto (#FF7A29)
    cuisine_type = db.Column(db.String(30), nullable=False, default='general')  # ver CUISINE_TYPES en app/utils/cover_bank.py
    plan_type = db.Column(db.String(20), default='emprendedor', nullable=False)
    subscription_expires_at = db.Column(AwareDateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    is_open = db.Column(db.Boolean, default=True, nullable=False)
    has_used_trial = db.Column(db.Boolean, default=False, nullable=False)
    # Configuración de expiración de pedidos pendientes (en horas, default 24)
    pending_expiry_hours = db.Column(db.Integer, default=24, nullable=False)
    ntfy_topic = db.Column(db.String(64), unique=True, nullable=True)
    created_at = db.Column(AwareDateTime, default=db.func.now())

    def __repr__(self):
        return f'<Restaurant {self.name}>'

    @property
    def is_subscription_active(self):
        """
        Verifica si la suscripción está activa
        Retorna True si: 
        - Tiene fecha de expiración Y
        - Esa fecha es mayor a la fecha actual (UTC)
        """
        if not self.subscription_expires_at:
            return False

        # Asegurar que la fecha de expiración sea aware (UTC)
        expires_at = self.subscription_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Comparar con la fecha actual (UTC)
        now_utc = datetime.now(timezone.utc)

        return expires_at > now_utc


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    # v2.0.0: ID de Clerk para lookup desde JWT (Scanner IA)
    clerk_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    # v2.1.0: Sistema de roles. Valores: owner | cashier | waiter.
    # Todos los usuarios existentes quedan como 'owner' vía server_default.
    role = db.Column(db.String(20), default='owner', nullable=False, server_default='owner')
    # PIN (hash) solo para empleados (cashier/waiter). El dueño no tiene PIN.
    pin_hash = db.Column(db.String(255), nullable=True)
    # v2.1.3: Protección contra fuerza bruta de PIN.
    failed_pin_attempts = db.Column(db.Integer, default=0, server_default='0', nullable=False)
    locked_until = db.Column(AwareDateTime, nullable=True)
    # Permite desactivar empleados sin borrarlos. El dueño siempre queda activo.
    is_active = db.Column(db.Boolean, default=True, server_default='1', nullable=False)

    # Relación con Restaurant
    restaurant = db.relationship('Restaurant', backref=db.backref('users', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    image_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relación con Restaurant
    restaurant = db.relationship('Restaurant', backref=db.backref('categories', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<Category {self.name}>'


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Integer, nullable=False)  # En pesos colombianos
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Badges del menú público (v1.5): resaltan atributos en la tarjeta.
    is_vegetarian = db.Column(db.Boolean, nullable=False, default=False)
    is_spicy = db.Column(db.Boolean, nullable=False, default=False)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)  # "Más pedido"
    image_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones
    restaurant = db.relationship('Restaurant', backref=db.backref('products', lazy=True, cascade='all, delete-orphan'))
    category = db.relationship('Category', backref=db.backref('products', lazy=True))

    def __repr__(self):
        return f'<Product {self.name}>'


class Modifier(db.Model):
    __tablename__ = 'modifiers'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    extra_price = db.Column(db.Integer, default=0, nullable=False)  # $0 o positivo
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones
    restaurant = db.relationship('Restaurant', backref=db.backref('modifiers', lazy=True, cascade='all, delete-orphan'))
    product = db.relationship('Product', backref=db.backref('modifiers', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<Modifier {self.name}>'


class Table(db.Model):
    __tablename__ = 'tables'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    qr_code = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    # Relación con Restaurant
    restaurant = db.relationship('Restaurant', backref=db.backref('tables', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<Table {self.name}>'
