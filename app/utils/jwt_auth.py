from flask import session as flask_session
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from app.models import User
from app.utils.restaurant import get_current_restaurant


def get_current_user_jwt():
    try:
        verify_jwt_in_request()
    except Exception:
        return None
    user_id = get_jwt_identity()
    if user_id:
        return User.query.get(user_id)
    return None


def get_current_restaurant_jwt():
    user = get_current_user_jwt()
    if user and user.restaurant:
        return user.restaurant
    # Fallback a la sesión del navegador (web sin JWT).
    return get_current_restaurant()
