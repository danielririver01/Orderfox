from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SubmitField, TextAreaField, BooleanField, SelectField, IntegerField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

class CategoryForm(FlaskForm):
    name = StringField('Nombre', validators=[
        DataRequired(message='Necesitamos un nombre para continuar.'),
        Length(max=100, message='El nombre es muy largo: usa máximo 100 letras.'),
    ])
    description = TextAreaField('Descripción')
    is_active = BooleanField('Activa', default=True)
    image = FileField('Imagen (Opcional)', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'],
                    'Ese archivo no es una imagen. Sube una foto JPG o PNG.')
    ])
    submit = SubmitField('Guardar')

class ProductForm(FlaskForm):
    name = StringField('Nombre', validators=[
        DataRequired(message='Necesitamos un nombre para continuar.'),
        Length(max=100, message='El nombre es muy largo: usa máximo 100 letras.'),
    ])
    category_id = SelectField('Categoría', coerce=int, validators=[
        DataRequired(message='Elige una categoría para saber dónde aparece este producto.'),
    ])
    price = IntegerField('Precio', validators=[
        DataRequired(message='Falta el precio. Escribe solo números, por ejemplo: 12000.'),
        NumberRange(min=1, message='El precio debe ser mayor a $0. Por ejemplo: 12000.'),
    ])
    description = TextAreaField('Descripción')
    is_active = BooleanField('Activo', default=True)
    # Badges del menú público (v1.5)
    is_vegetarian = BooleanField('Vegetariano', default=False)
    is_spicy = BooleanField('Picante', default=False)
    is_featured = BooleanField('Destacado (Más pedido)', default=False)
    image = FileField('Imagen (Opcional)', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'],
                    'Ese archivo no es una imagen. Sube una foto JPG o PNG.')
    ])
    submit = SubmitField('Guardar')

class ModifierForm(FlaskForm):
    name = StringField('Nombre', validators=[
        DataRequired(message='Ponle un nombre al combo para reconocerlo. Ejemplo: Doble carne.'),
        Length(max=50, message='El nombre del combo es muy largo: usa máximo 50 letras.'),
    ])
    extra_price = IntegerField('Precio Extra', validators=[
        NumberRange(min=0, message='El precio extra no puede ser negativo. Déjalo en 0 si no cuesta más.'),
    ], default=0)
    is_active = BooleanField('Activo', default=True)
    submit = SubmitField('Guardar')
