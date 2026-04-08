from app.models import Restaurant
from flask import session

from app.models import User
def get_current_restaurant():
    user_id = session.get('user_id')
    if user_id:
         user = User.query.get(user_id)
         if user and user.restaurant:
             return user.restaurant
    return None
