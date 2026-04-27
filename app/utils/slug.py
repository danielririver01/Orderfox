import re
import unicodedata

RESERVED_SLUGS = {
    'scanner-ia',
    'admin',
    'api',
    'dashboard',
    'velzia',
    'soporte',
    'login',
    'register',
    'logout',
    'static',
    'menu',
    'category',
    'product',
    'order',
    'webhook',
    'payment',
    'help',
    'helpcenter',
    'support',
    'privacy',
    'terms',
    'planes',
    'subscription',
    'profile',
    'settings',
    'billing',
    'root',
    'sysadmin',
    'system',
}

def slugify(text):
    """
    Convierte un texto en un slug amigable para URL.
    """
    if not text:
        return ""
    # Normalizar para eliminar acentos
    slug = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    # Eliminar caracteres no alfanuméricos, exceptuando guiones y espacios
    slug = re.sub(r'[^\w\s-]', '', slug).strip().lower()
    # Reemplazar espacios y guiones múltiples por un solo guión
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug

def is_slug_reserved(slug):
    """
    Verifica si un slug está en la lista de nombres reservados.
    """
    if not slug:
        return False
    return slug.lower() in RESERVED_SLUGS
