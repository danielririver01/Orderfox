from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from app.forms import ProductForm, ModifierForm
from app.models import db, Product, Modifier, Category
from app.utils.auth import login_required

from app.utils.restaurant import get_current_restaurant

products_bp = Blueprint('products', __name__, url_prefix='/products')

@products_bp.route('/')
@login_required
def index():
    """Listar todos los productos del restaurante agrupados por categoría"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    products = Product.query.filter_by(restaurant_id=restaurant.id).order_by(Product.category_id, Product.name).all()
    categories = Category.query.filter_by(restaurant_id=restaurant.id).all()
    return render_template('dashboard/products.html', products=products, categories=categories)

@products_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Crear nuevo producto"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    form = ProductForm()
    
    # Poblar el SelectField con las categorías del restaurante
    categories = Category.query.filter_by(restaurant_id=restaurant.id, is_active=True).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    
    if not categories:
        flash('Debes crear al menos una categoría antes de agregar productos', 'warning')
        return redirect(url_for('categories.index'))
    
    if form.validate_on_submit():
        # Validación crítica: verificar que category_id pertenece al restaurant
        category = Category.query.filter_by(id=form.category_id.data, restaurant_id=restaurant.id).first()
        if not category:
            flash('Categoría inválida', 'error')
            return redirect(url_for('products.create'))
        
        product = Product(
            restaurant_id=restaurant.id,
            category_id=form.category_id.data,
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            is_active=form.is_active.data
        )
        db.session.add(product)
        db.session.commit()
        flash('Producto creado exitosamente', 'success')
        return redirect(url_for('products.index'))
    
    return render_template('dashboard/product_form.html', form=form, title='Nuevo Producto')

@products_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Editar producto existente"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    form = ProductForm(obj=product)
    
    # Poblar el SelectField
    categories = Category.query.filter_by(restaurant_id=restaurant.id, is_active=True).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    
    if form.validate_on_submit():
        # Validación crítica
        category = Category.query.filter_by(id=form.category_id.data, restaurant_id=restaurant.id).first()
        if not category:
            flash('Categoría inválida', 'error')
            return redirect(url_for('products.edit', id=id))
        
        product.name = form.name.data
        product.category_id = form.category_id.data
        product.price = form.price.data
        product.description = form.description.data
        product.is_active = form.is_active.data
        db.session.commit()
        flash('Producto actualizado exitosamente', 'success')
        return redirect(url_for('products.index'))
    
    return render_template('dashboard/product_form.html', form=form, title='Editar Producto', product=product)

@products_bp.route('/<int:id>/toggle', methods=['PATCH'])
@login_required
def toggle(id):
    """Toggle is_active"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    data = request.get_json()
    product.is_active = data.get('is_active', not product.is_active)
    db.session.commit()
    
    return jsonify({'success': True, 'is_active': product.is_active})

@products_bp.route('/<int:id>/delete', methods=['POST', 'DELETE'])
@login_required
def delete(id):
    """Eliminar producto"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    db.session.delete(product)
    db.session.commit()
    flash('Producto eliminado exitosamente', 'success')
    
    return redirect(url_for('products.index'))

# ===== MODIFICADORES =====

@products_bp.route('/<int:product_id>/modifiers')
@login_required
def modifiers(product_id):
    """Listar modificadores de un producto"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    product = Product.query.filter_by(id=product_id, restaurant_id=restaurant.id).first_or_404()
    modifiers = Modifier.query.filter_by(product_id=product_id, restaurant_id=restaurant.id).all()
    
    return render_template('dashboard/product_modifiers.html', product=product, modifiers=modifiers)

@products_bp.route('/<int:product_id>/modifiers/create', methods=['GET', 'POST'])
@login_required
def create_modifier(product_id):
    """Crear modificador para un producto"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    product = Product.query.filter_by(id=product_id, restaurant_id=restaurant.id).first_or_404()
    form = ModifierForm()
    
    if form.validate_on_submit():
        modifier = Modifier(
            product_id=product_id,
            restaurant_id=restaurant.id,
            name=form.name.data,
            extra_price=form.extra_price.data,
            is_active=form.is_active.data
        )
        db.session.add(modifier)
        db.session.commit()
        flash('Modificador agregado exitosamente', 'success')
        return redirect(url_for('products.modifiers', product_id=product_id))
    
    return render_template('dashboard/modifier_form.html', form=form, product=product, title='Agregar Extra')

@products_bp.route('/modifiers/<int:id>/delete', methods=['POST', 'DELETE'])
@login_required
def delete_modifier(id):
    """Eliminar modificador"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    modifier = Modifier.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    product_id = modifier.product_id
    
    db.session.delete(modifier)
    db.session.commit()
    flash('Modificador eliminado exitosamente', 'success')
    
    return redirect(url_for('products.modifiers', product_id=product_id))
