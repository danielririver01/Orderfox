from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from app.models import db, Table, Restaurant
from app.utils.auth import login_required, active_required, feature_required
from app.utils.restaurant import get_current_restaurant
import qrcode
from io import BytesIO
from app.utils.subscription import check_feature_access
from PIL import Image, ImageFilter

tables_bp = Blueprint('tables', __name__, url_prefix='/dashboard/tables')

@tables_bp.route('/')
@login_required
@active_required
def index():
    restaurant = get_current_restaurant()
    tables = Table.query.filter_by(restaurant_id=restaurant.id).order_by(Table.created_at).all()
    
    # EL INDEX NO TIENE @feature_required para permitir mostrar el "Blur" (Upselling UX)
    has_table_qr_access = check_feature_access(restaurant, 'has_table_qr')
    
    return render_template('dashboard/tables.html', 
                         tables=tables, 
                         has_table_qr_access=has_table_qr_access)

@tables_bp.route('/create', methods=['POST'])
@login_required
@active_required
@feature_required('has_table_qr') # SEGURO: Bloqueo real en servidor
def create():
    restaurant = get_current_restaurant()
    name = request.form.get('name')
    
    if not name:
        flash('El nombre de la mesa es requerido', 'error')
        return redirect(url_for('tables.index'))
        
    table = Table(
        restaurant_id=restaurant.id,
        name=name,
        is_active=True
    )
    db.session.add(table)
    db.session.commit()
    
    flash('Mesa creada exitosamente', 'success')
    return redirect(url_for('tables.index'))

@tables_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@active_required
@feature_required('has_table_qr')
def delete(id):
    restaurant = get_current_restaurant()
    table = Table.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    db.session.delete(table)
    db.session.commit()
    
    flash('Mesa eliminada (el historial de pedidos se mantiene)', 'success')
    return redirect(url_for('tables.index'))

@tables_bp.route('/<int:id>/qr')
@login_required
@active_required
def qr(id):
    """
    Vista previa del QR de la mesa.
    Permite visualizar el QR, pero aplica blur si el plan no lo permite.
    NOTA: NO bloqueamos con @feature_required para permitir el Upselling visual.
    """
    restaurant = get_current_restaurant()
    table = Table.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    # Verificar acceso a QR de MESA
    has_table_qr_access = check_feature_access(restaurant, 'has_table_qr')
    
    # Generar URL completa del menú con mesa
    base_url = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    menu_url = f"{base_url}{url_for('public.menu', slug=restaurant.slug, table=table.id)}"
    
    # Generar URL de la imagen QR (para visualización)
    qr_image_url = url_for('tables.qr_image', id=table.id)
    
    return render_template('dashboard/qr_page.html', 
                         restaurant=restaurant, 
                         menu_url=menu_url,
                         qr_image_url=qr_image_url,
                         slug=restaurant.slug,
                         is_table_qr=True,
                         table_name=table.name,
                         has_qr_access=has_table_qr_access)



@tables_bp.route('/<int:id>/qr/image')
@login_required
@active_required
def qr_image(id):
    """
    Genera la imagen del QR para ser mostrada en la etiqueta <img>.
    PROTECCIÓN: Si no tiene permiso 'has_table_qr', devuelve una imagen difuminada (blur).
    """
    restaurant = get_current_restaurant()
    table = Table.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    # Verificar permisos (aquí es manual porque queremos devolver imagen difuminada, no error 403)
    has_access = check_feature_access(restaurant, 'has_table_qr')
    
    base_url = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    menu_url = f"{base_url}{url_for('public.menu', slug=restaurant.slug, table=table.id)}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(menu_url)
    qr.make(fit=True)
    
    # Convertir a imagen PIL para manipulación
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    if not has_access:
        # Aplicar blur severo en el servidor para inutilizar el QR
        img = img.filter(ImageFilter.GaussianBlur(radius=8))
    
    buffer = BytesIO()
    img.save(buffer, 'PNG')
    buffer.seek(0)
    
    return send_file(buffer, mimetype='image/png')

@tables_bp.route('/<int:id>/qr/download')
@login_required
@active_required
@feature_required('has_table_qr') # Bloqueo real en descarga
def download_qr(id):
    """
    Descarga el QR de la mesa como archivo.
    PROTEGIDO: Solo planes con 'has_table_qr' pueden descargar.
    """
    restaurant = get_current_restaurant()
    table = Table.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    
    base_url = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    menu_url = f"{base_url}{url_for('public.menu', slug=restaurant.slug, table=table.id)}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(menu_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, 'PNG')
    buffer.seek(0)
    
    return send_file(buffer, mimetype='image/png', as_attachment=True, download_name=f'Mesa-{table.name}.png')
