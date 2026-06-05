from flask import Blueprint, jsonify, request, current_app
from app.services.public_menu_service import PublicMenuService

menu_bp = Blueprint('menu', __name__, url_prefix='/menu')

@menu_bp.route('/<slug>/search-products')
def search_products(slug):
    """
    Endpoint para búsqueda global de productos
    Retorna TODOS los productos activos del restaurante con su categoría
    """
    try:
        restaurant, error = PublicMenuService.get_restaurant_by_slug(slug)
        if error:
            return jsonify({'success': False, 'error': 'Restaurante no encontrado', 'products': []}), 404

        if not restaurant.is_active:
            return jsonify({'success': False, 'error': 'Restaurante inactivo', 'products': []}), 403

        products_list, search_error = PublicMenuService.search_products_data(restaurant)
        if search_error:
            return jsonify({'success': False, 'error': search_error['message'], 'products': []}), 500

        return jsonify({'success': True, 'products': products_list, 'total': len(products_list)})

    except Exception as e:
        current_app.logger.error(f"Error in search_products: {e}")
        return jsonify({'success': False, 'error': 'Error interno del servidor', 'products': []}), 500


@menu_bp.route('/<slug>/search')
def search_by_query(slug):
    """
    Búsqueda con parámetro ?q=texto
    Ejemplo: /menu/mi-restaurante/search?q=hamburguesa
    """
    try:
        restaurant, error = PublicMenuService.get_restaurant_by_slug(slug)
        if error:
            return jsonify({'success': False, 'error': 'Restaurante no encontrado', 'products': []}), 404

        if not restaurant.is_active:
            return jsonify({'success': False, 'error': 'Restaurante inactivo', 'products': []}), 403

        query = request.args.get('q', '').lower().strip()

        if not query:
            return jsonify({'success': True, 'products': [], 'query': query})

        matching_products, search_error = PublicMenuService.search_products_by_query(restaurant, query)
        if search_error:
            return jsonify({'success': False, 'error': search_error['message'], 'products': []}), 500

        return jsonify({
            'success': True,
            'products': matching_products,
            'query': query,
            'total': len(matching_products)
        })

    except Exception as e:
        current_app.logger.error(f"Error in search_by_query: {e}")
        return jsonify({'success': False, 'error': 'Error interno del servidor', 'products': []}), 500
