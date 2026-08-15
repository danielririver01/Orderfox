from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SubmitField, TextAreaField, BooleanField, SelectField, IntegerField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

class CategoryForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Descripción')
    is_active = BooleanField('Activa', default=True)
    image = FileField('Imagen (Opcional)', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Solo imágenes!')
    ])
    submit = SubmitField('Guardar')

class ProductForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    category_id = SelectField('Categoría', coerce=int, validators=[DataRequired()])
    price = IntegerField('Precio', validators=[DataRequired(), NumberRange(min=1, message='El precio debe ser mayor a 0')])
    description = TextAreaField('Descripción')
    is_active = BooleanField('Activo', default=True)
    # Badges del menú público (v1.5)
    is_vegetarian = BooleanField('Vegetariano', default=False)
    is_spicy = BooleanField('Picante', default=False)
    is_featured = BooleanField('Destacado (Más pedido)', default=False)
    image = FileField('Imagen (Opcional)', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Solo imágenes!')
    ])
    submit = SubmitField('Guardar')

class ModifierForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired(), Length(max=50)])
    extra_price = IntegerField('Precio Extra', validators=[NumberRange(min=0, message='El precio debe ser 0 o positivo')], default=0)
    is_active = BooleanField('Activo', default=True)
    submit = SubmitField('Guardar')
