import os
import uuid
import io
from PIL import Image
from flask import current_app
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import cloudinary.api

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    if not filename:
        return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file, subfolder, max_size=(800, 800)):
    """
    Procesa y sube una imagen a Cloudinary.
    Comprime la imagen para mantenerla bajo el límite de 10MB de Cloudinary Free.
    """
    if not file or not allowed_file(file.filename):
        return None

    cloudinary.config(
        cloud_name = current_app.config.get('CLOUDINARY_CLOUD_NAME'),
        api_key = current_app.config.get('CLOUDINARY_API_KEY'),
        api_secret = current_app.config.get('CLOUDINARY_API_SECRET'),
        secure = True
    )

    try:
        img = Image.open(file.stream)
        
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        
        upload_result = cloudinary.uploader.upload(
            output,
            folder=f"velzia/{subfolder}",
            resource_type="image",
            transformation=[
                {"quality": "auto"},
                {"fetch_format": "auto"}
            ]
        )
        
        return upload_result.get('secure_url')
        
    except Exception as e:
        current_app.logger.error(f"Error al subir imagen a Cloudinary: {e}")
        return None

def delete_image(image_url):
    """
    Elimina la imagen de Cloudinary o del sistema local.
    - image_url: La URL completa de Cloudinary o la ruta relativa local.
    """
    if not image_url:
        return

    # Si es una URL de Cloudinary
    if 'cloudinary.com' in image_url:
        # Extraer public_id
        # Ejemplo: https://res.cloudinary.com/demo/image/upload/v12345/velzia/products/abc.jpg
        # El public_id sería 'velzia/products/abc'
        try:
            # Configurar Cloudinary
            cloudinary.config(
                cloud_name = current_app.config.get('CLOUDINARY_CLOUD_NAME'),
                api_key = current_app.config.get('CLOUDINARY_API_KEY'),
                api_secret = current_app.config.get('CLOUDINARY_API_SECRET'),
                secure = True
            )
            
            # El public_id es lo que está después de /upload/v[numero]/ y antes de la extensión
            parts = image_url.split('/')
            filename_with_ext = parts[-1]
            filename = filename_with_ext.rsplit('.', 1)[0]
            
            # Buscar el índice de 'upload' y obtener todo lo que sigue después de la versión (si existe)
            # Una forma más robusta con el SDK:
            # Pero como guardamos la URL completa, a veces es difícil reconstruir el public_id exacto si no conocemos la estructura.
            # En Cloudinary, el public_id incluye el folder.
            
            # Intentemos reconstruir el public_id asumiendo la estructura velzia/subfolder/filename
            # Si subfolder está en la URL
            if 'velzia' in image_url:
                start_index = image_url.find('velzia')
                public_id = image_url[start_index:].rsplit('.', 1)[0]
                cloudinary.uploader.destroy(public_id)
        except Exception as e:
            current_app.logger.error(f"Error al eliminar imagen de Cloudinary: {e}")
    else:
        # Construir ruta completa para eliminación local (compatibilidad con imágenes viejas)
        full_path = os.path.join(current_app.root_path, 'static', image_url)
        
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                current_app.logger.error(f"Error al eliminar imagen local {full_path}: {e}")
