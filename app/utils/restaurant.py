from app.models import Restaurant

def get_current_restaurant():
    # Para el MVP, devolvemos el primer restaurante.
    # Es vital no filtrar por is_active=True aquí, 
    # de lo contrario, si la tienda se cierra, el Dashboard dejará de funcionar (404).
    return Restaurant.query.first()
