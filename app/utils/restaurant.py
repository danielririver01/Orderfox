from app.models import Restaurant

def get_current_restaurant():
    from flask import session
    from app.models import User
    
    user_id = session.get('user_id')
    if user_id:
         user = User.query.get(user_id)
         if user and user.restaurant:
             return user.restaurant
             
    # Fallback: Si no hay usuario logueado (ej: tareas cron o errores), devolver None.
    # El dashboard abortará con 404 si recibe None.
    return None
