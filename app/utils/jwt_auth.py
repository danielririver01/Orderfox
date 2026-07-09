from flask_jwt_extended import get_jwt_identity
from app.models import User


def get_current_user_jwt():
    user_id = get_jwt_identity()
    if user_id:
        return User.query.get(user_id)
    return None


def get_current_restaurant_jwt():
    user = get_current_user_jwt()
    if user and user.restaurant:
        return user.restaurant
    return None
