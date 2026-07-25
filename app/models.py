from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

db = SQLAlchemy()
migrate = Migrate()

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

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.id', ondelete='SET NULL'), nullable=True)
    order_number = db.Column(db.String(20), nullable=False)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending', nullable=False)
    total = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)
    # IP del cliente para rate limiting (P4)
    ip_address = db.Column(db.String(45), nullable=True, index=True)
    # Fecha de expiración para pedidos pendientes
    expires_at = db.Column(AwareDateTime, nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # Relación con Restaurant y Table
    restaurant = db.relationship('Restaurant', backref=db.backref('orders', lazy=True, cascade='all, delete-orphan'))
    table = db.relationship('Table', backref=db.backref('orders', lazy=True)) # Sin cascade delete para preservar historial
    
    def __repr__(self):
        return f'<Order {self.order_number}>'

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=True)
    product_name = db.Column(db.String(100), nullable=False)
    product_price = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    modifiers_snapshot = db.Column(db.Text)
    subtotal = db.Column(db.Integer, nullable=False)
    
    # Relación con Order
    order = db.relationship('Order', backref=db.backref('items', lazy=True, cascade='all, delete-orphan'))
    restaurant = db.relationship('Restaurant', backref=db.backref('order_items', lazy=True, cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<OrderItem {self.product_name} x{self.quantity}>'

class TrialHistory(db.Model):
    __tablename__ = 'trial_history'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=True)
    whatsapp_phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<TrialHistory {self.email} - {self.whatsapp_phone}>'


# ─── Velzia 2.0.0: Sistema de Tokens IA ───────────────────────────────────────

class AITokenWallet(db.Model):
    """
    Billetera de tokens IA por usuario. Una fila por usuario.
    
    Regla "Fair Play":
    - plan_tokens: asignados por el plan mensual. Se resetean al renovar.
      Si es NULL → plan Elite (ilimitado), nunca se descuenta.
    - extra_tokens: comprados con top-up (MP). Se acumulan, no expiran.
    - El consumo descuenta primero plan_tokens, luego extra_tokens.
    """
    __tablename__ = 'ai_token_wallets'

    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                               nullable=False, unique=True)
    # NULL = Elite (ilimitado). MySQL no soporta Infinity en INT.
    plan_limit     = db.Column(db.Integer, nullable=True)
    plan_tokens    = db.Column(db.Integer, nullable=False, default=0)   # restantes del mes
    extra_tokens   = db.Column(db.Integer, nullable=False, default=0)   # comprados, sin expirar
    tokens_used_month = db.Column(db.Integer, nullable=False, default=0) # contador mensual
    reset_at       = db.Column(AwareDateTime, nullable=True)             # próx. reset
    created_at     = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at     = db.Column(AwareDateTime,
                               default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('token_wallet', uselist=False,
                                                       cascade='all, delete-orphan'))

    @property
    def is_elite(self):
        """Plan Elite = 3000 tokens (basado en plan_type del restaurant)."""
        return self.user.restaurant.plan_type == 'elite' if self.user.restaurant else False

    @property
    def total_available(self):
        """Tokens disponibles para usar ahora mismo."""
        return self.plan_tokens + self.extra_tokens

    @property
    def usage_percent(self):
        """Porcentaje de uso del plan mensual (0-100). None si no hay límite."""
        if not self.plan_limit:
            return None
        used = self.plan_limit - self.plan_tokens
        return round((used / self.plan_limit) * 100, 1)

    def can_scan(self):
        """¿El usuario puede hacer un escaneo ahora?"""
        return self.total_available > 0

    def __repr__(self):
        return (f'<AITokenWallet user={self.user_id} '
                f'plan={self.plan_tokens}/{self.plan_limit} extra={self.extra_tokens}>')


class AITokenTransaction(db.Model):
    """
    Log inmutable de cada operación de tokens.
    amount > 0 = recarga. amount < 0 = consumo.
    """
    __tablename__ = 'ai_token_transactions'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                              nullable=False)
    # Tipos: 'consume', 'topup_plan', 'topup_purchase', 'elite_scan'
    type          = db.Column(db.String(20), nullable=False)
    amount        = db.Column(db.Integer, nullable=False)  # +recarga / -consumo
    # Fuente: 'scanner_ia', 'plan_renewal', 'mp_purchase', 'migration_seed'
    source        = db.Column(db.String(50), nullable=False)
    mp_payment_id = db.Column(db.String(100), nullable=True, unique=True)
    description   = db.Column(db.String(200), nullable=True)
    created_at    = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('token_transactions', lazy='dynamic',
                                                       cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<AITokenTransaction user={self.user_id} type={self.type} amount={self.amount}>'

class PreRegistration(db.Model):
    __tablename__ = 'pre_registrations'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    selected_plan = db.Column(db.String(20), nullable=False, default='trial')
    whatsapp_phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<PreRegistration {self.email} - {self.selected_plan}>'


class OrderCounter(db.Model):
    """Atomic counter for order numbers per restaurant per day (P5)."""
    __tablename__ = 'order_counters'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    counter = db.Column(db.Integer, nullable=False, default=0)
    __table_args__ = (db.UniqueConstraint('restaurant_id', 'date', name='uq_restaurant_date'),)

    restaurant = db.relationship('Restaurant', backref=db.backref('order_counters', lazy=True,
                                                                   cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<OrderCounter restaurant={self.restaurant_id} date={self.date} count={self.counter}>'


class Expense(db.Model):
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(50), default='otros')
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    
    restaurant = db.relationship('Restaurant', backref=db.backref('expenses', lazy=True, cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<Expense {self.description} ${self.amount}>'



# ─── Copilot VZ: Conversaciones y Mensajes de IA ─────────────────────────────
# Postulado de diseno:
#   "PostgreSQL calcula, Flask organiza, la IA interpreta."
# - CopilotConversation: una sesion de analisis del restaurante.
# - CopilotMessage: cada turno (usuario o asistente).
# - prompt_version + model se guardan para poder cambiar el prompt sin romper
#   el historial de conversaciones anteriores.

class CopilotConversation(db.Model):
    __tablename__ = 'copilot_conversations'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(200), nullable=True)
    prompt_version = db.Column(db.String(10), default='v1.0')
    model = db.Column(db.String(50), default='deepseek-chat')
    analysis_active = db.Column(db.Boolean, default=False, nullable=False)
    pinned = db.Column(db.Boolean, default=False, nullable=False)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    restaurant = db.relationship('Restaurant', backref=db.backref('copilot_conversations', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('copilot_conversations', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<CopilotConversation {self.id} title={self.title}>'


class CopilotMessage(db.Model):
    __tablename__ = 'copilot_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('copilot_conversations.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    conversation = db.relationship('CopilotConversation', backref=db.backref('messages', lazy='dynamic', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<CopilotMessage {self.id} [{self.role}]>'


class CopilotBusinessEvent(db.Model):
    __tablename__ = 'copilot_business_events'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = db.Column(db.String(50), nullable=False, index=True)
    priority = db.Column(db.SmallInteger, default=0, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    preview = db.Column(db.String(300), nullable=False)
    template_key = db.Column(db.String(50), nullable=False)
    template_data = db.Column(db.Text, nullable=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('copilot_conversations.id', ondelete='SET NULL'), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))
    consumed_at = db.Column(AwareDateTime, nullable=True)
    dismissed_at = db.Column(AwareDateTime, nullable=True)

    restaurant = db.relationship('Restaurant', backref=db.backref('copilot_events', lazy='dynamic', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<CopilotBusinessEvent {self.id} kind={self.kind} p={self.priority}>'


class RewardClaim(db.Model):
    """Recompensa generada tras pago (Sorpresa Velzia)."""
    __tablename__ = 'reward_claims'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.String(36), unique=True, nullable=False, index=True)
    plan_key = db.Column(db.String(50), nullable=False)
    rarity = db.Column(db.String(20), nullable=False)
    reward_type = db.Column(db.String(50), nullable=False)
    reward_value = db.Column(db.Integer, nullable=True)
    reward_label = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False)
    claimed_at = db.Column(AwareDateTime, nullable=True)
    created_at = db.Column(AwareDateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('reward_claims', lazy='dynamic', cascade='all, delete-orphan'))
    restaurant = db.relationship('Restaurant', backref=db.backref('reward_claims', lazy='dynamic', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<RewardClaim {self.id} {self.rarity}/{self.reward_type} for user {self.user_id}>'
