from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort, current_app
from app.forms import ProductForm
from app.models import Product
from app.utils.auth import require_auth, require_active, require_role_check

from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import check_feature_access, get_plan_limits
from app.services.product_service import ProductService
from app.services.category_service import CategoryService
from app.services.auto_photo_service import AutoPhotoService

products_bp = Blueprint('products', __name__, url_prefix='/products')


@products_bp.before_request
def _require_dashboard_owner():
    """Todas las rutas de productos son del dueño: bloquea empleados (v2.1.1)."""
    return require_role_check('owner')


@products_bp.route('/')
@require_auth
@require_active
def index():
    """Listar todos los productos del restaurante agrupados por categoría"""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    products, _ = ProductService.get_products_for_restaurant(restaurant.id)
    categories = CategoryService.get_categories(restaurant.id)
    plan_limits = get_plan_limits(restaurant.plan_type)
    current_active_count = ProductService.get_active_count(restaurant.id)
    has_modifiers_access = check_feature_access(restaurant, 'has_modifiers')

    return render_template('dashboard/products.html',
                           products=products,
                           categories=categories,
                           plan_limits=plan_limits,
                           current_active_count=current_active_count,
                           has_modifiers_access=has_modifiers_access)


@products_bp.route('/category/<int:category_id>')
@require_auth
@require_active
def by_category(category_id):
    """Ver productos de una categoría con paginación"""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    category = CategoryService.get_category(restaurant.id, category_id)
    if not category:
        abort(404)

    page = request.args.get('page', 1, type=int)
    per_page = 6

    pagination = ProductService.get_products_paginated(restaurant.id, category_id, page=page, per_page=per_page)

    plan_limits = get_plan_limits(restaurant.plan_type)
    current_active_count = ProductService.get_active_count(restaurant.id)
    has_modifiers_access = check_feature_access(restaurant, 'has_modifiers')

    return render_template('dashboard/products_category.html',
                           category=category,
                           products=pagination.items,
                           pagination=pagination,
                           plan_limits=plan_limits,
                           current_active_count=current_active_count,
                           has_modifiers_access=has_modifiers_access)


@products_bp.route('/create', methods=['GET', 'POST'])
@require_auth
@require_active
def create():
    """Crear nuevo producto"""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    form = ProductForm()

    categories = CategoryService.get_active_categories(restaurant.id)
    form.category_id.choices = [(c.id, c.name) for c in categories]

    # Pre-seleccionar categoría si viene en los argumentos
    category_id_arg = request.args.get('category_id', type=int)
    if category_id_arg and any(c.id == category_id_arg for c in categories):
        form.category_id.data = category_id_arg

    if not categories:
        flash('Primero crea una categoría para poder agregar productos '
              'o activa una categoría existente', 'warning')
        return redirect(url_for('categories.index'))

    if form.validate_on_submit():
        product, error = ProductService.create_product(
            restaurant_id=restaurant.id,
            category_id=form.category_id.data,
            name=form.name.data,
            price=form.price.data,
            description=form.description.data,
            is_active=form.is_active.data,
            image_file=form.image.data,
            is_vegetarian=form.is_vegetarian.data,
            is_spicy=form.is_spicy.data,
            is_featured=form.is_featured.data,
        )
        if error:
            flash(error, 'error')
            return redirect(url_for('products.create'))

        # Auto-asignar foto si no se subió una
        if not product.image_url:
            AutoPhotoService.enqueue(
                current_app._get_current_object(),
                product.id,
                product.name,
                product.restaurant_id,
            )

        flash('Producto creado exitosamente', 'success')
        return redirect(url_for('products.by_category',
                                category_id=product.category_id))

    return render_template('dashboard/product_form.html',
                           form=form, title='Nuevo Producto')


@products_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@require_auth
@require_active
def edit(id):
    """Editar producto existente"""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        abort(404)

    form = ProductForm(obj=product)

    categories = CategoryService.get_active_categories(restaurant.id)
    form.category_id.choices = [(c.id, c.name) for c in categories]

    # Forzar la seleccion correcta con GET
    if request.method == "GET":
        form.category_id.data = product.category_id

    if form.validate_on_submit():
        product, error = ProductService.update_product(
            product=product,
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            category_id=form.category_id.data,
            is_active=form.is_active.data,
            image_file=form.image.data,
            delete_image_flag=request.form.get('delete_image') == 'true',
            is_vegetarian=form.is_vegetarian.data,
            is_spicy=form.is_spicy.data,
            is_featured=form.is_featured.data,
        )
        if error:
            flash(error, 'error')
            return redirect(url_for('products.edit', id=id))

        flash('Producto actualizado exitosamente', 'success')
        return redirect(url_for('products.by_category',
                                category_id=product.category_id))

    return render_template('dashboard/product_form.html',
                           form=form, title='Editar Producto',
                           product=product)


@products_bp.route('/<int:id>/status', methods=['GET'])
@require_auth
@require_active
def get_status(id):
    """Obtener el estado actual de un producto"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404

    status_data = ProductService.get_product_status(product)
    return jsonify({'success': True, **status_data})


@products_bp.route('/<int:id>/status', methods=['PUT', 'POST'])
@require_auth
@require_active
def update_status(id):
    """Actualizar el estado is_active con validación de límites"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404

    data = request.get_json()
    if not data or 'is_active' not in data:
        return jsonify({'error': 'Datos inválidos'}), 400

    desired_state = data.get('is_active')

    # Save original state to detect if change occurred
    original_active = product.is_active

    product, error, limit_blocked = ProductService.toggle_product(
        product, desired_state
    )
    if error:
        return jsonify({
            'success': False,
            'message': error,
            'is_active': product.is_active
        }), 400

    # If state didn't change, respond without message
    if product.is_active == original_active:
        return jsonify({'success': True, 'is_active': product.is_active})

    return jsonify({
        'success': True,
        'is_active': product.is_active,
        'message': 'Estado actualizado correctamente'
    })


@products_bp.route('/<int:id>/swap-photo', methods=['PATCH', 'POST'])
@require_auth
@require_active
def swap_photo(id):
    """1-Click Swap para fotos sugeridas automáticamente"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404

    result = AutoPhotoService.swap_suggested(id, restaurant.id)
    if not result.get('success'):
        return jsonify(result), 400

    return jsonify(result)


@products_bp.route('/<int:id>/toggle', methods=['PATCH', 'POST'])
@require_auth
@require_active
def toggle(id):
    """Mantenemos compatibilidad con el endpoint anterior si es necesario"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404

    data = request.get_json(silent=True) or request.form
    desired_state = data.get('is_active')

    if isinstance(desired_state, str):
        desired_state = desired_state.lower() in ('true', '1', 'yes')

    product, error, limit_blocked = ProductService.toggle_product(
        product, desired_state
    )
    if error:
        return jsonify({
            'success': False,
            'message': error,
            'is_active': product.is_active
        }), 400

    return jsonify({'success': True, 'is_active': product.is_active})


@products_bp.route('/<int:id>/delete', methods=['POST', 'DELETE'])
@require_auth
@require_active
def delete(id):
    """Eliminar producto"""
    restaurant = get_current_restaurant()
    if not restaurant:
        abort(404)

    product = ProductService.get_product(restaurant.id, id)
    if not product:
        abort(404)

    category_id = product.category_id
    ProductService.delete_product(product)
    flash('Producto eliminado exitosamente', 'success')

    return redirect(url_for('products.by_category', category_id=category_id))


# ===== MODIFICADORES =====

# ─── Session-based API for Modifiers Modal ─────────────────────────────────


@products_bp.route('/<int:product_id>/api/modifiers', methods=['GET'])
@require_auth
@require_active
def api_list_modifiers(product_id):
    """Listar modificadores de un producto (session auth)"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    product = ProductService.get_product(restaurant.id, product_id)
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    modifiers = ProductService.get_modifiers_for_product(
        restaurant.id, product_id
    )

    return jsonify({
        'success': True,
        'data': {
            'modifiers': [
                {
                    'id': m.id,
                    'name': m.name,
                    'extra_price': m.extra_price,
                    'is_active': m.is_active,
                }
                for m in modifiers
            ]
        }
    })


@products_bp.route('/<int:product_id>/api/modifiers', methods=['POST'])
@require_auth
@require_active
def api_create_modifier(product_id):
    """Crear modificador (session auth)"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    if not check_feature_access(restaurant, 'has_modifiers'):
        return jsonify({
            'success': False,
            'error': 'Tu plan no incluye Modificadores'
        }), 403

    product = ProductService.get_product(restaurant.id, product_id)
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400

    name = data.get('name', '').strip()
    extra_price = data.get('extra_price', 0)

    if not name:
        return jsonify({'success': False, 'error': 'Nombre es requerido'}), 400

    modifier, error = ProductService.create_modifier(
        restaurant_id=restaurant.id,
        product_id=product_id,
        name=name,
        extra_price=extra_price,
    )
    if error:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({
        'success': True,
        'data': {
            'id': modifier.id,
            'name': modifier.name,
            'extra_price': modifier.extra_price,
            'is_active': modifier.is_active,
        }
    }), 201


@products_bp.route('/api/modifiers/<int:id>/toggle', methods=['PATCH'])
@require_auth
@require_active
def api_toggle_modifier(id):
    """Activar/desactivar modificador (session auth)"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    modifier = ProductService.get_modifier(restaurant.id, id)
    if not modifier:
        return jsonify({'success': False, 'error': 'Modifier no encontrado'}), 404

    ProductService.toggle_modifier(modifier)

    return jsonify({
        'success': True,
        'data': {
            'id': modifier.id,
            'name': modifier.name,
            'extra_price': modifier.extra_price,
            'is_active': modifier.is_active,
        }
    })


@products_bp.route('/api/modifiers/<int:id>', methods=['DELETE'])
@require_auth
@require_active
def api_delete_modifier(id):
    """Eliminar modificador (session auth)"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404

    modifier = ProductService.get_modifier(restaurant.id, id)
    if not modifier:
        return jsonify({'success': False, 'error': 'Modifier no encontrado'}), 404

    ProductService.delete_modifier(modifier)

    return jsonify({
        'success': True,
        'message': 'Modifier eliminado exitosamente'
    })
