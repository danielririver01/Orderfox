from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired

class LoginForm(FlaskForm):
    email = StringField('Email',  validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    submit = SubmitField('Enviar instrucciones')

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
    password = PasswordField('Contraseña', validators=[DataRequired()])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[DataRequired()])
    submit = SubmitField('Finalizar y Pagar')
