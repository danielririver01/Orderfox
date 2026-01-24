from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from app.forms import CategoryForm
from app.models import db, Category
from app.utils.auth import login_required

from app.utils.restaurant import get_current_restaurant

categories_bp = Blueprint('categories', __name__, url_prefix='/categories')

@categories_bp.route('/')
@login_required
def index():
    """Listar todas las categorías del restaurante"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    categories = Category.query.filter_by(restaurant_id=restaurant.id).order_by(Category.sort_order).all()
    return render_template('dashboard/categories.html', categories=categories)

@categories_bp.route('/create', methods=['GET', 'POST'])
@login_required
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
        db.session.add(category)
        db.session.commit()
        flash('Categoría creada exitosamente', 'success')
        return redirect(url_for('categories.index'))
    
    return render_template('dashboard/category_form.html', form=form, title='Nueva Categoría')

@categories_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
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
        db.session.commit()
        flash('Categoría actualizada exitosamente', 'success')
        return redirect(url_for('categories.index'))
    
    return render_template('dashboard/category_form.html', form=form, title='Editar Categoría', category=category)

@categories_bp.route('/<int:id>/toggle', methods=['PATCH'])
@login_required
def toggle(id):
    """Toggle is_active (UI Optimista)"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    category = Category.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    data = request.get_json()
    category.is_active = data.get('is_active', not category.is_active)
    db.session.commit()
    
    return jsonify({'success': True, 'is_active': category.is_active})

@categories_bp.route('/<int:id>/reorder', methods=['PATCH'])
@login_required
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
    
    db.session.delete(category)
    db.session.commit()
    flash('Categoría eliminada exitosamente', 'success')
    
    return redirect(url_for('categories.index'))

