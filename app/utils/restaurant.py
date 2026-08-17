from app.models import Restaurant
from flask import session

from app.models import User
def get_current_restaurant():
    # v2.1.2: el dueño (user_id) tiene prioridad si ambas claves coexisten en
    # el mismo navegador. Normalmente solo existe una (última acción de login
    # limpia la clave del otro rol).
    user_id = session.get('user_id')
    employee_id = session.get('employee_id')
    if user_id:
         user = User.query.get(user_id)
         if user and user.restaurant:
             return user.restaurant
    if employee_id:
         user = User.query.get(employee_id)
         if user and user.restaurant:
             return user.restaurant
    return None
