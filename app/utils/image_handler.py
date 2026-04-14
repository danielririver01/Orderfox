import os
import uuid
from PIL import Image
from flask import current_app
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file, subfolder, max_size=(800, 800)):
    """
    Procesa y guarda una imagen localmente.
    - file: El objeto de archivo de Flask (request.files['image'])
    - subfolder: 'products' o 'categories'
    - max_size: Tupla (width, height) para redimensionar proporcionalmente
    
    Retorna la ruta relativa para guardar en la BD, o None si falla.
    """
    if not file or not allowed_file(file.filename):
        return None

    # Asegurar que el nombre de archivo es seguro y unico
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    
    # Crear ruta completa del archivo
    # Usamos os.path.join con la configuracion de Flask
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder)
    
    # Asegurar que el directorio existe
    if not os.path.exists(upload_path):
        os.makedirs(upload_path, exist_ok=True)
        
    full_path = os.path.join(upload_path, filename)
    
    try:
        # Procesar con Pillow
        img = Image.open(file)
        
        # Convertir a RGB si es necesario (ej. de RGBA/PNG a JPEG)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        # Redimensionar manteniendo el ratio
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Guardar
        img.save(full_path, optimize=True, quality=85)
        
        # Retornar ruta relativa desde static
        # static/uploads/<subfolder>/<filename>
        return f"uploads/{subfolder}/{filename}"
        
    except Exception as e:
        print(f"Error al procesar imagen: {e}")
        return None

def delete_image(image_url):
    """
    Elimina el archivo físico de una imagen.
    - image_url: La ruta relativa guardada en la BD (ej. uploads/products/abc.jpg)
    """
    if not image_url:
        return
        
    # Construir ruta completa
    # image_url viene como 'uploads/products/filename.ext'
    # static está un nivel arriba de uploads en la config
    full_path = os.path.join(current_app.root_path, 'static', image_url)
    
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
        except Exception as e:
            print(f"Error al eliminar imagen {full_path}: {e}")
