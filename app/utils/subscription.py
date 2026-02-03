
PLAN_LIMITS = {
    'emprendedor': {
        'max_products': 25,
        'has_qr': False,
        'has_modifiers': False,
        'has_status_management': False,
        'name': 'Emprendedor'
    },
    'crecimiento': {
        'max_products': 100,
        'has_qr': True,
        'has_modifiers': False,
        'has_status_management': True,
        'name': 'Crecimiento'
    },
    'elite': {
        'max_products': float('inf'),
        'has_qr': True,
        'has_modifiers': True,
        'has_status_management': True,
        'name': 'Élite'
    }
}

def get_plan_limits(plan_type):
    return PLAN_LIMITS.get(plan_type, PLAN_LIMITS['emprendedor'])

def check_feature_access(restaurant, feature):
    """
    Verifica si un restaurante tiene acceso a una característica específica.
    feature options: 'has_qr', 'has_modifiers', 'has_status_management'
    """
    if not restaurant: return False
    limits = get_plan_limits(restaurant.plan_type)
    return limits.get(feature, False)

def check_product_limit(restaurant):
    """
    Verifica si el restaurante ha alcanzado su límite de productos.
    Retorna (Boolean, Mensaje)
    """
    if not restaurant: return False, "Restaurante no encontrado"
    
    limits = get_plan_limits(restaurant.plan_type)
    max_products = limits['max_products']
    
    # Si es infinito, siempre permitir
    if max_products == float('inf'):
         return True, "Ilimitado"

    current_count = len(restaurant.products)
    
    if current_count >= max_products:
        return False, f"Has alcanzado el límite de {max_products} productos de tu plan {limits['name']}."
    
    return True, f"Te quedan {max_products - current_count} productos."
