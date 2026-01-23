from flask import Blueprint, render_template

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
def index():
    return render_template('dashboard/index.html')

@dashboard_bp.route('/Productos')
def productos():
    return render_template('dashboard/productos.html')

