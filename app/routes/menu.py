# Agregar este endpoint a tu blueprint de menu (menu.py o routes/menu.py)

from flask import Blueprint, jsonify
from app.models import Product, Category, Restaurant
from app.utils.subscription import is_subscription_active

menu_bp = Blueprint('menu', __name__, url_prefix='/menu')

@menu_bp.route('/<slug>/search-products')
def search_products(slug):
    """
    Endpoint para búsqueda global de productos
    Retorna TODOS los productos activos del restaurante con su categoría
    """
    try:
        # Obtener restaurante por slug
        restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
        
        # VALIDACIÓN DE SEGURIDAD
        if not is_subscription_active(restaurant):
            return jsonify({'success': False, 'error': 'Suscripción inactiva', 'products': []}), 403
        
        # Obtener todas las categorías activas del restaurante
        categories = Category.query.filter_by(
            restaurant_id=restaurant.id,
            is_active=True
        ).all()
        
        # Construir lista de todos los productos
        products_list = []
        
        for category in categories:
            # Obtener productos activos de cada categoría
            products = Product.query.filter_by(
                category_id=category.id,
                is_active=True
            ).all()
            
            for product in products:
                products_list.append({
                    'id': product.id,
                    'name': product.name,
                    'description': product.description,
                    'price': product.price,
                    'category_id': category.id,
                    'category_name': category.name,
                    'has_modifiers': len(product.modifiers) > 0 if hasattr(product, 'modifiers') else False
                })
        
        return jsonify({'success': True,'products': products_list,'total': len(products_list)})
        
    except Exception as e:
        return jsonify({'success': False,'error': str(e),'products': []}), 500


# ALTERNATIVA: Si quieres búsqueda con query string
@menu_bp.route('/<slug>/search')
def search_by_query(slug):
    """
    Búsqueda con parámetro ?q=texto
    Ejemplo: /menu/mi-restaurante/search?q=hamburguesa
    """
    try:
        restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
        
        # VALIDACIÓN DE SEGURIDAD
        if not is_subscription_active(restaurant):
            return jsonify({'success': False, 'error': 'Suscripción inactiva', 'products': []}), 403
        query = request.args.get('q', '').lower().strip()
        
        if not query:
            return jsonify({'success': True,'products': [],'query': query})
        
        # Buscar productos que coincidan
        categories = Category.query.filter_by(
            restaurant_id=restaurant.id,
            is_active=True
        ).all()
        
        matching_products = []
        
        for category in categories:
            products = Product.query.filter_by(
                category_id=category.id,
                is_active=True
            ).all()
            
            for product in products:
                # Buscar en nombre, descripción y nombre de categoría
                searchable_text = f"{product.name} {product.description or ''} {category.name}".lower()
                
                if query in searchable_text:
                    matching_products.append({
                        'id': product.id,
                        'name': product.name,
                        'description': product.description,
                        'price': product.price,
                        'category_id': category.id,
                        'category_name': category.name,
                        'has_modifiers': len(product.modifiers) > 0 if hasattr(product, 'modifiers') else False
                    })
        
        return jsonify({
            'success': True,
            'products': matching_products,
            'query': query,
            'total': len(matching_products)
        })
        
    except Exception as e:
        return jsonify({'success': False,'error': str(e),'products': []}), 500