from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from app.forms import ProductForm, ModifierForm
from app.models import db, Product, Modifier, Category
from app.utils.auth import login_required, active_required

from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import check_product_limit, check_feature_access, get_plan_limits
from app.utils.image_handler import save_image, delete_image

products_bp = Blueprint('products', __name__, url_prefix='/products')

@products_bp.route('/')
@login_required
@active_required
def index():
    """Listar todos los productos del restaurante agrupados por categoría"""
    from flask import abort
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    products = Product.query.filter_by(restaurant_id=restaurant.id).order_by(Product.category_id, Product.name).all()
    categories = Category.query.filter_by(restaurant_id=restaurant.id).all()
    plan_limits = get_plan_limits(restaurant.plan_type)
    current_active_count = Product.query.filter_by(restaurant_id=restaurant.id, is_active=True).count()
    return render_template('dashboard/products.html', products=products, categories=categories, plan_limits=plan_limits, current_active_count=current_active_count)

@products_bp.route('/category/<int:category_id>')
@login_required
@active_required
def by_category(category_id):
    """Ver productos de una categoría con paginación"""
    from flask import abort

    restaurant = get_current_restaurant()
    if not restaurant: abort(404)

    category = Category.query.filter_by(id=category_id, restaurant_id=restaurant.id).first_or_404()

    page = request.args.get('page', 1, type=int)
    per_page = 6

    pagination = Product.query.filter_by(
        category_id=category_id,
        restaurant_id=restaurant.id
    ).order_by(Product.name).paginate(page=page, per_page=per_page, error_out=False)

    plan_limits = get_plan_limits(restaurant.plan_type)
    current_active_count = Product.query.filter_by(restaurant_id=restaurant.id, is_active=True).count()

    return render_template('dashboard/products_category.html',
                         category=category,
                         products=pagination.items,
                         pagination=pagination,
                         plan_limits=plan_limits,
                         current_active_count=current_active_count)

@products_bp.route('/create', methods=['GET', 'POST'])
@login_required
@active_required
def create():
    """Crear nuevo producto"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    allowed, message = check_product_limit(restaurant)
    if not allowed:
        flash(message, 'warning')
        return redirect(url_for('products.index'))

    form = ProductForm()
    
    categories = Category.query.filter_by(restaurant_id=restaurant.id, is_active=True).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    
    if not categories:
        flash('Primero crea una categoría para poder agregar productos o activa una categoría existente', 'warning')
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
            is_active=form.is_active.data,
            is_highlighted=form.is_highlighted.data
        )
        
        # Manejo de imagen
        if form.image.data:
            image_url = save_image(form.image.data, 'products')
            if image_url:
                product.image_url = image_url
        
        db.session.add(product)
        db.session.commit()
        flash('Producto creado exitosamente', 'success')
        return redirect(url_for('products.index'))
    
    return render_template('dashboard/product_form.html', form=form, title='Nuevo Producto')

@products_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@active_required
def edit(id):
    """Editar producto existente"""
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    form = ProductForm(obj=product)
    
    categories = Category.query.filter_by(restaurant_id=restaurant.id, is_active=True).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    
    #Forzar la seleccion correcta con GET
    if request.method == "GET":
        form.category_id.data = product.category_id

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
        product.is_highlighted = form.is_highlighted.data
        
        # Manejo de imagen
        if form.image.data:
            # Eliminar imagen anterior si existe
            if product.image_url:
                delete_image(product.image_url)
            
            image_url = save_image(form.image.data, 'products')
            if image_url:
                product.image_url = image_url
        elif request.form.get('delete_image') == 'true':
            if product.image_url:
                delete_image(product.image_url)
            product.image_url = None
        
        db.session.commit()
        flash('Producto actualizado exitosamente', 'success')
        return redirect(url_for('products.index'))
    
    return render_template('dashboard/product_form.html', form=form, title='Editar Producto', product=product)


@products_bp.route('/<int:id>/status', methods=['GET'])
@login_required
@active_required
def get_status(id):
    """Obtener el estado actual de un producto"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404

    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404

    return jsonify({
        'success': True,
        'id': product.id,
        'is_active': product.is_active
    })

@products_bp.route('/<int:id>/status', methods=['PUT', 'POST'])
@login_required
@active_required
def update_status(id):
    """Actualizar el estado is_active con validación de límites"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404

    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404

    data = request.get_json()
    if not data or 'is_active' not in data:
        return jsonify({'error': 'Datos inválidos'}), 400

    desired_state = data.get('is_active')

    # Si se intenta activar, verificar límites del plan
    if desired_state is True and product.is_active is False:
        allowed, message = check_product_limit(restaurant)
        if not allowed:
            return jsonify({
                'success': False,
                'message': message,
                'is_active': product.is_active
            }), 400

    if product.is_active == desired_state:
        return jsonify({'success': True, 'is_active': product.is_active})

    product.is_active = desired_state
    db.session.commit()

    return jsonify({
        'success': True,
        'is_active': product.is_active,
        'message': 'Estado actualizado correctamente'
    })

@products_bp.route('/<int:id>/toggle', methods=['PATCH', 'POST'])
@login_required
@active_required
def toggle(id):
    """Mantenemos compatibilidad con el endpoint anterior si es necesario"""
    restaurant = get_current_restaurant()
    if not restaurant:
        return jsonify({'error': 'Restaurante no encontrado'}), 404
    
    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404
    
    data = request.get_json(silent=True) or request.form
    desired_state = data.get('is_active')
    
    if isinstance(desired_state, str):
        desired_state = desired_state.lower() in ('true', '1', 'yes')
    
    if desired_state is None:
        desired_state = not product.is_active

    if desired_state is True and product.is_active is False:
        allowed, message = check_product_limit(restaurant)
        if not allowed:
            return jsonify({
                'success': False, 
                'message': message,
                'is_active': product.is_active
            }), 400

    if product.is_active == desired_state:
        return jsonify({'success': True, 'is_active': product.is_active})
    
    product.is_active = desired_state
    db.session.commit()
    
    return jsonify({'success': True, 'is_active': product.is_active})
@products_bp.route('/<int:id>/delete', methods=['POST', 'DELETE'])
@login_required
@active_required
def delete(id):
    """Eliminar producto"""
    from flask import abort
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    product = Product.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    # Eliminar imagen física antes de borrar de la BD
    if product.image_url:
        delete_image(product.image_url)
        
    db.session.delete(product)
    db.session.commit()
    flash('Producto eliminado exitosamente', 'success')
    
    return redirect(url_for('products.index'))

# ===== MODIFICADORES =====

@products_bp.route('/<int:product_id>/modifiers')
@login_required
@active_required
def modifiers(product_id):
    """Listar modificadores de un producto"""
    from flask import abort
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    product = Product.query.filter_by(id=product_id, restaurant_id=restaurant.id).first_or_404()
    modifiers = Modifier.query.filter_by(product_id=product_id, restaurant_id=restaurant.id).all()
    
    has_modifiers_access = check_feature_access(restaurant, 'has_modifiers')
    
    return render_template('dashboard/product_modifiers.html', 
                         product=product, 
                         modifiers=modifiers,
                         has_modifiers_access=has_modifiers_access)

@products_bp.route('/<int:product_id>/modifiers/create', methods=['GET', 'POST'])
@login_required
@active_required
def create_modifier(product_id):
    """Crear modificador para un producto"""
    from flask import abort
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    
    # Security Check: Plan Élite required
    if not check_feature_access(restaurant, 'has_modifiers'):
        flash(f'Tu plan {restaurant.plan_type.capitalize()} no incluye Modificadores. Actualiza a Élite para desbloquear esta función.', 'warning')
        return redirect(url_for('products.modifiers', product_id=product_id))

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
@active_required
def delete_modifier(id):
    """Eliminar modificador"""
    from flask import abort
    restaurant = get_current_restaurant()
    if not restaurant: abort(404)
    modifier = Modifier.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    product_id = modifier.product_id
    
    db.session.delete(modifier)
    db.session.commit()
    flash('Modificador eliminado exitosamente', 'success')
    
    return redirect(url_for('products.modifiers', product_id=product_id))
