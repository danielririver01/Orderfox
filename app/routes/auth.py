from flask import Blueprint, render_template, redirect, url_for, flash
from app.forms import LoginForm, ForgotPasswordForm
from app.models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            # Aquí se implementará la sesión posteriormente
            user.password_hash = None # Seguridad básica, no enviar hash a la vista si no es necesario
            return redirect(url_for('dashboard.index'))
        else:
            flash('Email o contraseña incorrectos')
    return render_template('auth/index.html', form=form)

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            flash('Se han enviado las instrucciones a tu correo.')
        else:
            flash('No se encontró una cuenta con ese correo.')
    return render_template('auth/forgot_password.html', form=form)

@auth_bp.route('/logout')
def logout():
    return redirect(url_for('auth.login'))


