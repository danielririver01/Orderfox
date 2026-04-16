from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from app.forms import CategoryForm
from app.models import db, Category
from app.utils.auth import login_required, active_required

from app.utils.restaurant import get_current_restaurant
from app.utils.image_handler import save_image, delete_image

categories_bp = Blueprint('categories', __name__, url_prefix='/categories')

@categories_bp.route('/')
@login_required
@active_required
def index():
    """Listar todas las categorías del restaurante"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    categories = Category.query.filter_by(restaurant_id=restaurant.id).order_by(Category.sort_order).all()
    return render_template('dashboard/categories.html', categories=categories)

@categories_bp.route('/create', methods=['GET', 'POST'])
@login_required
@active_required
def create():
    """Crear nueva categoría"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    form = CategoryForm()
    if form.validate_on_submit():
        max_order = db.session.query(db.func.max(Category.sort_order)).filter_by(restaurant_id=restaurant.id).scalar() or 0
        
        category = Category(
            restaurant_id=restaurant.id,
            name=form.name.data,
            description=form.description.data,
            is_active=form.is_active.data,
            sort_order=max_order + 1
        )
        
        # Manejo de imagen
        if form.image.data:
            image_url = save_image(form.image.data, 'categories')
            if image_url:
                category.image_url = image_url
                
        db.session.add(category)
        db.session.commit()
        flash('Categoría creada exitosamente', 'success')
        return redirect(url_for('categories.index'))
    
    return render_template('dashboard/category_form.html', form=form, title='Nueva Categoría')

@categories_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@active_required
def edit(id):
    """Editar categoría existente"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    form = CategoryForm(obj=category)
    
    if form.validate_on_submit():
        category.name = form.name.data
        category.description = form.description.data
        category.is_active = form.is_active.data
        
        # Manejo de imagen
        if form.image.data:
            # Eliminar imagen anterior si existe
            if category.image_url:
                delete_image(category.image_url)
            
            image_url = save_image(form.image.data, 'categories')
            if image_url:
                category.image_url = image_url
        elif request.form.get('delete_image') == 'true':
            if category.image_url:
                delete_image(category.image_url)
            category.image_url = None
                
        db.session.commit()
        flash('Categoría actualizada exitosamente', 'success')
        return redirect(url_for('categories.index'))
    
    return render_template('dashboard/category_form.html', form=form, title='Editar Categoría', category=category)

@categories_bp.route('/<int:id>/status', methods=['GET'])
@login_required
@active_required
def get_status(id):
    """Obtener el estado actual de una categoría"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404

    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not category:
        return jsonify({'error': 'Categoría no encontrada'}), 404

    return jsonify({
        'success': True,
        'id': category.id,
        'is_active': category.is_active
    })

@categories_bp.route('/<int:id>/status', methods=['PUT', 'POST'])
@login_required
@active_required
def update_status(id):
    """Actualizar el estado is_active de una categoría"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404

    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not category:
        return jsonify({'error': 'Categoría no encontrada'}), 404

    data = request.get_json()
    if not data or 'is_active' not in data:
        return jsonify({'error': 'Datos inválidos'}), 400

    category.is_active = data.get('is_active')
    db.session.commit()

    return jsonify({
        'success': True,
        'is_active': category.is_active,
        'message': 'Estado de categoría actualizado'
    })

@categories_bp.route('/<int:id>/toggle', methods=['PATCH'])
@login_required
@active_required
def toggle(id):
    """Mantenemos para compatibilidad"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    data = request.get_json()
    category.is_active = data.get('is_active', not category.is_active)
    db.session.commit()
    
    return jsonify({'success': True, 'is_active': category.is_active})

@categories_bp.route('/<int:id>/reorder', methods=['PATCH'])
@login_required
@active_required
def reorder(id):
    """Cambiar orden de la categoría"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    data = request.get_json()
    new_order = data.get('sort_order')
    
    if new_order is not None:
        category.sort_order = new_order
        db.session.commit()
        return jsonify({'success': True, 'sort_order': category.sort_order})
    
    return jsonify({'success': False, 'error': 'sort_order requerido'}), 400

@categories_bp.route('/<int:id>/delete', methods=['POST', 'DELETE'])
@login_required
@active_required
def delete(id):
    """Eliminar categoría"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    # Validación: verificar que no tenga productos asociados
    from app.models import Product
    product_count = Product.query.filter_by(category_id=id, restaurant_id=restaurant.id).count()
    
    if product_count > 0:
        flash(f'No puedes eliminar esta categoría porque tiene {product_count} producto(s) asociado(s).', 'error')
        return redirect(url_for('categories.index'))
    
    # Eliminar imagen física antes de borrar de la BD
    if category.image_url:
        delete_image(category.image_url)
        
    db.session.delete(category)
    db.session.commit()
    flash('Categoría eliminada exitosamente', 'success')
    
    return redirect(url_for('categories.index'))

