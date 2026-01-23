from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()
migrate = Migrate()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    """ role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    role = db.relationship('Role', backref=db.backref('users', lazy=True)) """ # Se usara para el futuro no es necesario ahora 
    
    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

# Se usara para el futuro no es necesario ahora 
# class Role(db.Model):
#     __tablename__ = 'roles'
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(180), unique=True, nullable=False)
    

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, nullable=False)  # Futuro: FK a restaurants
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    
    def __repr__(self):
        return f'<Category {self.name}>'

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Integer, nullable=False)  # En pesos colombianos
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    
    # Relación con Category
    category = db.relationship('Category', backref=db.backref('products', lazy=True))
    
    def __repr__(self):
        return f'<Product {self.name}>'

class Modifier(db.Model):
    __tablename__ = 'modifiers'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    restaurant_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    extra_price = db.Column(db.Integer, default=0, nullable=False)  # $0 o positivo
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    
    # Relación con Product
    product = db.relationship('Product', backref=db.backref('modifiers', lazy=True, cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<Modifier {self.name}>'

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, nullable=False)
    order_number = db.Column(db.String(20), nullable=False)  # ORD-001
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, kitchen, delivered, cancelled
    total = db.Column(db.Integer, nullable=False)  # Total en pesos
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    
    def __repr__(self):
        return f'<Order {self.order_number}>'

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)  # Snapshot
    product_price = db.Column(db.Integer, nullable=False)     # Snapshot
    quantity = db.Column(db.Integer, default=1, nullable=False)
    modifiers_snapshot = db.Column(db.Text)  # JSON con modificadores
    subtotal = db.Column(db.Integer, nullable=False)
    
    # Relación con Order
    order = db.relationship('Order', backref=db.backref('items', lazy=True, cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<OrderItem {self.product_name} x{self.quantity}>'

