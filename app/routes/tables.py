from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app, abort
from app.utils.auth import login_required, active_required, feature_required
from app.utils.restaurant import get_current_restaurant
from app.utils.subscription import check_feature_access
from app.services.table_service import TableService
import qrcode
from io import BytesIO
from PIL import Image, ImageFilter
import unicodedata, re

tables_bp = Blueprint('tables', __name__, url_prefix='/dashboard/tables')

@tables_bp.route('/')
@login_required
@active_required
def index():
    restaurant = get_current_restaurant()
    tables = TableService.get_tables(restaurant.id)
    # No @feature_required here — allows showing Blur (Upselling UX)
    has_table_qr_access = check_feature_access(restaurant, 'has_table_qr')
    return render_template('dashboard/tables.html',
                         tables=tables,
                         has_table_qr_access=has_table_qr_access)

@tables_bp.route('/create', methods=['POST'])
@login_required
@active_required
@feature_required('has_table_qr')
def create():
    restaurant = get_current_restaurant()
    name = request.form.get('name')
    table, error = TableService.create_table(restaurant.id, name)
    if error:
        flash(error, 'error')
        return redirect(url_for('tables.index'))
    flash('Mesa creada exitosamente', 'success')
    return redirect(url_for('tables.index'))

@tables_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@active_required
@feature_required('has_table_qr')
def delete(id):
    restaurant = get_current_restaurant()
    table = TableService.get_table(restaurant.id, id)
    if not table:
        abort(404)
    # Web route: delete without checking active orders
    TableService.delete_table(table, check_active_orders=False)
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
    table = TableService.get_table(restaurant.id, id)
    if not table:
        abort(404)
    has_table_qr_access = check_feature_access(restaurant, 'has_table_qr')
    base_url = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    menu_url = f"{base_url}{url_for('public.menu', slug=restaurant.slug, table=table.id)}"
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
    table = TableService.get_table(restaurant.id, id)
    if not table:
        abort(404)
    has_access = check_feature_access(restaurant, 'has_table_qr')
    base_url = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    menu_url = f"{base_url}{url_for('public.menu', slug=restaurant.slug, table=table.id)}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(menu_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    if not has_access:
        img = img.filter(ImageFilter.GaussianBlur(radius=8))
    buffer = BytesIO()
    img.save(buffer, 'PNG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png')

@tables_bp.route('/<int:id>/qr/download')
@login_required
@active_required
@feature_required('has_table_qr')
def download_qr(id):
    """
    Descarga el QR de la mesa como archivo.
    PROTEGIDO: Solo planes con 'has_table_qr' pueden descargar.
    """
    restaurant = get_current_restaurant()
    table = TableService.get_table(restaurant.id, id)
    if not table:
        abort(404)
    base_url = current_app.config.get('BASE_URL') or request.host_url.rstrip('/')
    menu_url = f"{base_url}{url_for('public.menu', slug=restaurant.slug, table=table.id)}"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(menu_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, 'PNG')
    buffer.seek(0)
    safe_name = unicodedata.normalize('NFKD', table.name)
    safe_name = safe_name.encode('ascii', 'ignore').decode('ascii')
    safe_name = re.sub(r'[^\w\s-]', '', safe_name).strip()
    safe_name = re.sub(r'[\s]+', '-', safe_name)
    filename = f"QR-{safe_name}.png" if safe_name else f"QR-mesa-{table.id}.png"
    return send_file(buffer, mimetype='image/png', as_attachment=True, download_name=filename)
