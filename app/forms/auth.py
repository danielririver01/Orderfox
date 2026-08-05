from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError


def password_complexity_check(form, field):
    password = field.data
    if not password:
        return
    if not password[0].isupper():
        raise ValidationError('La contraseña debe empezar con una letra mayúscula.')
    if not any(char.isdigit() for char in password):
        raise ValidationError('La contraseña debe incluir al menos un número.')

class LoginForm(FlaskForm):
    email = StringField('Email',  validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RegisterEmailForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    submit = SubmitField('Verificar email')

class RegisterVerifyForm(FlaskForm):
    code = StringField('Código', validators=[DataRequired()])
    submit = SubmitField('Verificar código')

class RegisterSetupForm(FlaskForm):
    admin_name = StringField('Nombre del Administrador', validators=[DataRequired()])
    restaurant_name = StringField('Nombre del Restaurante', validators=[DataRequired()])
    phone = StringField('Teléfono', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[
        DataRequired(),
        Length(min=8, message='La contraseña debe tener al menos 8 caracteres.'),
        password_complexity_check
    ])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[
        DataRequired(),
        EqualTo('password', message='Las contraseñas deben coincidir.')
    ])
    accept_terms = BooleanField('Acepto los Términos y Condiciones y la Política de Datos')
    submit = SubmitField('Finalizar y Pagar')
