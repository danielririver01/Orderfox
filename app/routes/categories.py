from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from app.forms import CategoryForm
from app.utils.auth import require_auth, require_active, require_role_check
from app.utils.restaurant import get_current_restaurant
from app.services.category_service import CategoryService

categories_bp = Blueprint('categories', __name__, url_prefix='/categories')


@categories_bp.before_request
def _require_dashboard_owner():
    """Todas las rutas de categorías son del dueño: bloquea empleados (v2.1.1)."""
    return require_role_check('owner')

@categories_bp.route('/')
@require_auth
@require_active
def index():
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    categories = CategoryService.get_categories(restaurant.id)
    return render_template('dashboard/categories.html', categories=categories)

@categories_bp.route('/create', methods=['GET', 'POST'])
@require_auth
@require_active
def create():
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    form = CategoryForm()
    if form.validate_on_submit():
        category, error = CategoryService.create_category(
            restaurant_id=restaurant.id,
            name=form.name.data,
            description=form.description.data,
            is_active=form.is_active.data,
            image_file=form.image.data
        )
        if error:
            flash(error, 'error')
            return redirect(url_for('categories.create'))
        flash('Categoría creada exitosamente', 'success')
        return redirect(url_for('products.by_category', category_id=category.id))
    return render_template('dashboard/category_form.html', form=form, title='Nueva Categoría')

@categories_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@require_auth
@require_active
def edit(id):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    category = CategoryService.get_category(restaurant.id, id)
    if not category: abort(404)
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
        category, error = CategoryService.update_category(
            category=category,
            name=form.name.data,
            description=form.description.data,
            is_active=form.is_active.data,
            image_file=form.image.data,
            delete_image_flag=request.form.get('delete_image') == 'true'
        )
        if error:
            flash(error, 'error')
            return redirect(url_for('categories.edit', id=id))
        flash('Categoría actualizada exitosamente', 'success')
        return redirect(url_for('products.by_category', category_id=category.id))
    return render_template('dashboard/category_form.html', form=form, title='Editar Categoría', category=category)

@categories_bp.route('/<int:id>/status', methods=['GET'])
@require_auth
@require_active
def get_status(id):
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404
    category = CategoryService.get_category(restaurant.id, id)
    if not category:
        return jsonify({'error': 'Categoría no encontrada'}), 404
    return jsonify({'success': True, 'id': category.id, 'is_active': category.is_active})

@categories_bp.route('/<int:id>/status', methods=['PUT', 'POST'])
@require_auth
@require_active
def update_status(id):
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404
    category = CategoryService.get_category(restaurant.id, id)
    if not category:
        return jsonify({'error': 'Categoría no encontrada'}), 404
    data = request.get_json()
    if not data or 'is_active' not in data:
        return jsonify({'error': 'Datos inválidos'}), 400
    CategoryService.toggle_category(category, data.get('is_active'))
    return jsonify({'success': True, 'is_active': category.is_active, 'message': 'Estado de categoría actualizado'})

@categories_bp.route('/<int:id>/toggle', methods=['PATCH'])
@require_auth
@require_active
def toggle(id):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    category = CategoryService.get_category(restaurant.id, id)
    if not category: abort(404)
    data = request.get_json()
    CategoryService.toggle_category(category, data.get('is_active'))
    return jsonify({'success': True, 'is_active': category.is_active})

@categories_bp.route('/<int:id>/reorder', methods=['PATCH'])
@require_auth
@require_active
def reorder(id):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    category = CategoryService.get_category(restaurant.id, id)
    if not category: abort(404)
    data = request.get_json()
    success, error = CategoryService.reorder_category(category, data.get('sort_order'))
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'sort_order': category.sort_order})

@categories_bp.route('/<int:id>/delete', methods=['POST', 'DELETE'])
@require_auth
@require_active
def delete(id):
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    category = CategoryService.get_category(restaurant.id, id)
    if not category: abort(404)
    success, error = CategoryService.delete_category(category)
    if not success:
        flash(error, 'error')
        return redirect(url_for('categories.index'))
    flash('Categoría eliminada exitosamente', 'success')
    return redirect(url_for('categories.index'))
