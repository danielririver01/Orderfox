from flask import Blueprint, render_template, redirect, url_for, flash, session
from app.forms import LoginForm, ForgotPasswordForm
from app.models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            session['username'] = user.username
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
            flash('No pudimos validar la información ingresada. Revisa tus datos e inténtalo de nuevo')
    return render_template('auth/forgot_password.html', form=form)

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente')
    return redirect(url_for('auth.login'))
