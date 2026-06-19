# GUIDE-06: Referencia de Variables de Entorno

**Versión:** 1.0 | **Fecha:** 2026-06-16 | **Propietario:** Equipo Técnico

---

## 1. Variables Obligatorias

| Variable | Descripción | Valor por Defecto | ¿Dónde Obtenerla? |
|----------|-------------|-------------------|-------------------|
| `SECRET_KEY` | Clave de cifrado de sesiones CSRF | `una-clave-secreta-muy-larga-para-desarrollo-seguro` | Generar con `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Conexión a MySQL | `mysql+pymysql://root:@localhost/orderfox` | Configuración de BD en hosting |
| `MAIL_USERNAME` | Correo Gmail para envíos | — | Cuenta Gmail del equipo |
| `MAIL_PASSWORD` | Contraseña de aplicación Gmail | — | [Google App Passwords](https://myaccount.google.com/apppasswords) |

---

## 2. Integraciones Externas

### Clerk (Autenticación OAuth)

| Variable | Descripción | ¿Dónde Obtenerla? |
|----------|-------------|-------------------|
| `CLERK_PUBLISHABLE_KEY` | Clave pública de Clerk | Dashboard de Clerk > API Keys |
| `CLERK_SECRET_KEY` | Clave secreta de Clerk | Dashboard de Clerk > API Keys |
| `CLERK_JWT_ISSUER` | Emisor de JWT de Clerk | `https://<instance>.clerk.accounts.dev` (Dashboard) |

### Cloudinary (Imágenes)

| Variable | Descripción | ¿Dónde Obtenerla? |
|----------|-------------|-------------------|
| `CLOUDINARY_CLOUD_NAME` | Nombre del cloud | Dashboard de Cloudinary |
| `CLOUDINARY_API_KEY` | API Key | Dashboard de Cloudinary |
| `CLOUDINARY_API_SECRET` | API Secret | Dashboard de Cloudinary |

### Mercado Pago (Pagos)

| Variable | Descripción | ¿Dónde Obtenerla? |
|----------|-------------|-------------------|
| `MP_ACCESS_TOKEN` | Token de acceso (producción) | Dashboard MP > Credenciales |
| `MP_PUBLIC_KEY` | Llave pública (frontend) | Dashboard MP > Credenciales |

### Scanner IA (AI Externa)

| Variable | Descripción | Valor por Defecto |
|----------|-------------|-------------------|
| `SCANNER_IA_URL` | URL del servicio Scanner IA | `http://localhost:3000` |
| `SERVICE_API_KEY` | API Key para comunicación server-to-server | Generar aleatoriamente |

---

## 3. Configuración General

| Variable | Descripción | Default | Notas |
|----------|-------------|---------|-------|
| `BASE_URL` | URL base del dominio | — | Usar ngrok URL en dev, dominio real en prod. Necesario para QRs |
| `FLASK_DEBUG` | Modo debug de Flask | `False` | `True` solo en desarrollo |
| `SUPPORT_EMAIL` | Correo de soporte al cliente | `soporte@velzia.com` | Se muestra en páginas de error |
| `SUPPORT_PHONE` | Teléfono de soporte | `+573000000000` | Se muestra en páginas de error |

---

## 4. Configuración de Correo

| Variable | Descripción | Default | Notas |
|----------|-------------|---------|-------|
| `MAIL_SERVER` | Servidor SMTP | `smtp.gmail.com` | Cambiar si no es Gmail |
| `MAIL_PORT` | Puerto SMTP | `587` | 587 para TLS, 465 para SSL |
| `MAIL_USE_TLS` | Usar TLS | `True` | Deshabilitar si se usa SSL |
| `MAIL_DEFAULT_SENDER` | Remitente por defecto | `MAIL_USERNAME` | Opcional, si es distinto del usuario |

---

## 5. JWT (API Móvil)

| Variable | Descripción | Default | Notas |
|----------|-------------|---------|-------|
| `JWT_SECRET_KEY` | Clave para firmar JWT | `SECRET_KEY` | Puede ser la misma o una diferente |
| `JWT_ACCESS_TOKEN_EXPIRES` | Expiración de access token | 24 horas | Configurable en `settings.py` |
| `JWT_REFRESH_TOKEN_EXPIRES` | Expiración de refresh token | 7 días | Configurable en `settings.py` |

---

## 6. Archivo .env de Ejemplo

```bash
# Flask
SECRET_KEY=tu-clave-secreta-aqui
FLASK_DEBUG=False
BASE_URL=https://tudominio.com

# Base de Datos
DATABASE_URL=mysql+pymysql://usuario:password@localhost/orderfox

# Correo
MAIL_USERNAME=tu-correo@gmail.com
MAIL_PASSWORD=tu-contraseña-app
MAIL_DEFAULT_SENDER=soporte@velzia.com

# Clerk
CLERK_PUBLISHABLE_KEY=pk_xxxxxx
CLERK_SECRET_KEY=sk_xxxxxx

# Cloudinary
CLOUDINARY_CLOUD_NAME=tu-cloud
CLOUDINARY_API_KEY=123456
CLOUDINARY_API_SECRET=abcdef

# Mercado Pago
MP_ACCESS_TOKEN=APP_USR-xxxxxx
MP_PUBLIC_KEY=APP_USR-xxxxxx

# Scanner IA
SCANNER_IA_URL=http://localhost:3000
SERVICE_API_KEY=clave-secreta-para-scanner-ia

# Soporte
SUPPORT_EMAIL=soporte@velzia.com
SUPPORT_PHONE=+573000000000
```

---

## 7. Verificación

Para verificar que todas las variables necesarias están configuradas:

```bash
python -c "
from settings import Config
c = Config()
required = ['SECRET_KEY', 'DATABASE_URL', 'MAIL_USERNAME', 'MAIL_PASSWORD',
            'CLERK_SECRET_KEY', 'CLOUDINARY_CLOUD_NAME', 'MP_ACCESS_TOKEN',
            'SERVICE_API_KEY']
for var in required:
    val = getattr(c, var, None)
    status = '✅' if val else '❌'
    print(f'{status} {var}: {\"[set]\" if val else \"[MISSING]\"}')"
```

---

## 8. Historial de Cambios

| Fecha | Versión | Cambio | Autor |
|-------|---------|--------|-------|
| 2026-06-16 | 1.0 | Versión inicial | Auditoría Documental |
