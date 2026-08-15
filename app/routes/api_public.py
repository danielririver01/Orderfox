from flask import Blueprint, jsonify, request
from app.services.public_menu_service import PublicMenuService

api_public_bp = Blueprint('api_public', __name__, url_prefix='/api/public')


@api_public_bp.route('/menu/<string:slug>', methods=['GET'])
def get_menu(slug):
    restaurant, error = PublicMenuService.get_restaurant_by_slug(slug)
    if error:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    # Rediseño menú público: un restaurante cerrado muestra el menú con
    # is_open=false (badge "Cerrado", botones de agregar deshabilitados en el
    # frontend). Los pedidos siguen bloqueados server-side en /api/order.
    menu_data = PublicMenuService.get_menu_api_data(restaurant)
    if menu_data is None:
        return jsonify({'success': False, 'error': 'Error al cargar el menú'}), 500

    return jsonify({'success': True, 'data': menu_data})


@api_public_bp.route('/menu/<string:slug>/categoria/<int:category_id>', methods=['GET'])
def get_category_products(slug, category_id):
    restaurant, error = PublicMenuService.get_restaurant_by_slug(slug)
    if error:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    category_data, products_data = PublicMenuService.get_category_products_data(
        restaurant, category_id
    )
    if not category_data:
        return jsonify({'success': False, 'error': 'Categoría no encontrada'}), 404

    return jsonify({
        'success': True,
        'data': {
            'category': category_data,
            'products': products_data
        }
    })


@api_public_bp.route('/menu/<string:slug>/novedades', methods=['GET'])
def get_novedades(slug):
    restaurant, error = PublicMenuService.get_restaurant_by_slug(slug)
    if error:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)

    products_data, pagination = PublicMenuService.get_novedades_data(
        restaurant, page=page, per_page=per_page
    )

    return jsonify({
        'success': True,
        'data': {
            'products': products_data,
            'pagination': pagination
        }
    })
