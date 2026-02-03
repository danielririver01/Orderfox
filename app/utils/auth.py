from functools import wraps
from flask import session, redirect, url_for, flash
from datetime import datetime
from app import db

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, inicia sesión para acceder a esta página.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def active_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.utils.restaurant import get_current_restaurant
        restaurant = get_current_restaurant()
        if not restaurant or not restaurant.is_active:
            # Si el restaurante no está activo, forzar pago
            # Guardamos el ID en sesión por si acaso el flujo de pago lo necesita
            if restaurant:
                session['pending_restaurant_id'] = restaurant.id
                session['setup_done'] = True # Para que la ruta /payment lo deje entrar
            
            flash('Tu suscripción no está activa. Por favor completa el pago para continuar.', 'warning')
            return redirect(url_for('auth.payment'))
            
        # Verificar fecha de expiración
        if restaurant.subscription_expires_at and restaurant.subscription_expires_at < datetime.now():
            restaurant.is_active = False
            db.session.commit()
            
            session['pending_restaurant_id'] = restaurant.id
            session['setup_done'] = True
            
            flash('Tu plan ha vencido. Por favor renueva tu suscripción.', 'warning')
            return redirect(url_for('auth.payment'))

        return f(*args, **kwargs)
    return decorated_function
