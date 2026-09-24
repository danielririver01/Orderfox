import os
import uuid
import io
from PIL import Image, UnidentifiedImageError
from flask import current_app
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import cloudinary.api

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_FORMATS = {'JPEG', 'JPG', 'PNG', 'WEBP'}

# Límite anti-bomba de descompresión: 150MP cubre cámaras de 108MP pero
# bloquea imágenes gigantes que agotarían la RAM al decodificar. Pillow
# lanza DecompressionBombError al superarlo (se captura en save_image).
# NUNCA volver a None: desactiva la protección global del proceso.
Image.MAX_IMAGE_PIXELS = 150_000_000
MAX_IMAGE_PIXELS = 150_000_000
# Tope de bytes leídos del stream (defensa en profundidad junto al
# MAX_CONTENT_LENGTH=16MB de Flask, que puede no aplicar a tests o
# a llamadas internas).
MAX_IMAGE_BYTES = 16 * 1024 * 1024

def allowed_file(filename):
    if not filename:
        return False
    # Sanitizar antes de validar: evita "foto.jpg\x00.png" y rarezas.
    filename = secure_filename(filename)
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
        # Leer el stream con tope de bytes (defensa en profundidad).
        raw = file.stream.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            current_app.logger.warning(
                'Imagen rechazada (%s): supera %d bytes',
                secure_filename(file.filename or 'unknown'), MAX_IMAGE_BYTES,
            )
            return None
        if not raw:
            return None
        try:
            img = Image.open(io.BytesIO(raw))
            img.load()  # fuerza decodificación aquí, dentro del try
        except Image.DecompressionBombError:
            current_app.logger.warning(
                'Imagen rechazada (%s): bomba de descompresión (>%d px)',
                secure_filename(file.filename or 'unknown'), MAX_IMAGE_PIXELS,
            )
            return None
        except (UnidentifiedImageError, OSError, ValueError) as e:
            current_app.logger.warning(
                'Imagen rechazada (%s): no es imagen válida (%s)',
                secure_filename(file.filename or 'unknown'), e,
            )
            return None

        # Formato real (magic bytes), no solo extensión.
        if (img.format or '').upper() not in ALLOWED_FORMATS:
            current_app.logger.warning(
                'Imagen rechazada (%s): formato %s no permitido',
                secure_filename(file.filename or 'unknown'), img.format,
            )
            return None

        # Cinturón extra aunque Pillow ya limita por píxeles totales.
        w, h = img.size
        if w * h > MAX_IMAGE_PIXELS or w <= 0 or h <= 0:
            current_app.logger.warning(
                'Imagen rechazada (%s): dimensiones %dx%d exceden el límite',
                secure_filename(file.filename or 'unknown'), w, h,
            )
            return None
        
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
        filename = secure_filename(file.filename) if file and file.filename else 'unknown'
        current_app.logger.error(
            f"Error al subir imagen a Cloudinary ({filename}): {e}"
        )
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
                # Allowlist estricta: solo nuestros prefijos, sin '..' ni
                # caracteres de traversal. Evita destroy arbitrario vía URL
                # manipulada (p. ej. ".../velzia/../../otro").
                if ('..' in public_id or public_id.startswith('/')
                        or not public_id.startswith('velzia/')):
                    current_app.logger.warning(
                        'Borrado Cloudinary rechazado: public_id fuera de allowlist (%s)',
                        public_id,
                    )
                    return
                cloudinary.uploader.destroy(public_id)
        except Exception as e:
            current_app.logger.error(f"Error al eliminar imagen de Cloudinary: {e}")
    else:
        # Borrado local (compatibilidad con imágenes viejas).
        # Anti-traversal: solo rutas relativas dentro de app/static, nunca
        # URLs absolutas ni escapes con '..'. Se canonicaliza con realpath
        # (resuelve symlinks) y se exige que quede bajo el dir permitido.
        lowered = image_url.strip().lower()
        if (lowered.startswith(('http://', 'https://', 'data:', 'blob:'))
                or os.path.isabs(image_url)
                or '..' in image_url.split('/')):
            current_app.logger.warning(
                'Borrado local rechazado: ruta fuera de allowlist (%s)', image_url,
            )
            return
        static_dir = os.path.realpath(os.path.join(current_app.root_path, 'static'))
        full_path = os.path.realpath(os.path.join(static_dir, image_url.lstrip('/')))
        if full_path != static_dir and not full_path.startswith(static_dir + os.sep):
            current_app.logger.warning(
                'Borrado local rechazado: escape de static (%s)', image_url,
            )
            return
        
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                current_app.logger.error(f"Error al eliminar imagen local {full_path}: {e}")
