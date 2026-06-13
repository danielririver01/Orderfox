# Guía de Inicio Rápido — Velzia

> **Dos proyectos, un ecosistema.** Sigue estos pasos para poner todo en funcionamiento.

## Requisitos Previos

| Herramienta | Versión | Motivo |
|------------|---------|--------|
| Python | 3.10+ | Flask backend |
| Node.js | 20+ | Next.js frontend |
| pnpm | 8+ | Package manager Next.js |
| MySQL | 8+ | Base de datos |
| Git | — | Control de versiones |

## 1. Clonar Repositorios

```bash
# Proyecto principal (Flask)
git clone https://github.com/danielririver01/Orderfox.git
cd Orderfox

# Scanner IA (Next.js) — en paralelo, al mismo nivel
git clone https://github.com/danielririver01/Receipt-Scanner-AI.git
```

**Estructura esperada:**
```
/Orderfox/
/Receipt-Scanner-AI/
```

## 2. Configurar Base de Datos

```sql
CREATE DATABASE orderfox CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 3. Ordenfox (Flask)

### 3.1 Entorno Virtual
```bash
cd Orderfox
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # Windows
# source .venv/bin/activate       # Linux/Mac
```

### 3.2 Dependencias
```bash
pip install -r requirements.txt
```

### 3.3 Variables de Entorno
Crear `.env` en la raíz de Orderfox:

```ini
SECRET_KEY=tu_clave_secreta_aqui
DATABASE_URL=mysql+pymysql://root:password@localhost/orderfox

# Clerk Auth
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...

# Email (Gmail)
MAIL_USERNAME=tu_correo@gmail.com
MAIL_PASSWORD=contraseña_app

# Cloudinary
CLOUDINARY_CLOUD_NAME=tu_cloud
CLOUDINARY_API_KEY=123456
CLOUDINARY_API_SECRET=abc123

# Mercado Pago
MP_ACCESS_TOKEN=APP_USR-...
MP_PUBLIC_KEY=APP_USR-...

# URLs
BASE_URL=http://localhost:5000
SCANNER_IA_URL=http://localhost:3000

# API Key compartida (misma en ambos proyectos)
SERVICE_API_KEY=73d285f32a0b1047d7962c61c3ea4d26af771d9d139bf6939fdaf17d8c053b67
```

### 3.4 Migraciones
```bash
flask db upgrade
```

### 3.5 Tailwind CSS
```bash
npm install
npm run build:css
# Para desarrollo: npm run watch:css
```

### 3.6 Ejecutar
```bash
python run.py
# → http://localhost:5000
```

## 4. Scanner IA (Next.js)

### 4.1 Dependencias
```bash
cd Receipt-Scanner-AI
pnpm install
```

### 4.2 Variables de Entorno
Crear `.env` en la raíz de Receipt-Scanner-AI:

```ini
# Clerk Auth (MISMO publishable key que en Flask)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...

# API Keys
DEEPSEEK_API_KEY=sk-deepseek...
GOOGLE_VISION_API_KEY=AIza...
SERVICE_API_KEY=73d285f32a0b1047d7962c61c3ea4d26af771d9d139bf6939fdaf17d8c053b67

# JWT compartido (MISMO secret que en Flask)
FLASK_SECRET_KEY=...misma que SECRET_KEY de Flask...

# Base de datos (MISMA que Flask)
DATABASE_URL=mysql://root:password@localhost:3306/orderfox?connection_limit=2

# URLs
ORDERFOX_URL=http://localhost:5000
NEXT_PUBLIC_FLASK_REGISTER_URL=http://localhost:5000/register
NEXT_PUBLIC_VELZIA_URL=http://localhost:5000
NEXT_PUBLIC_ORDERFOX_URL=http://localhost:5000
```

### 4.3 Prisma
```bash
npx prisma generate
npx prisma db push
# o si hay migraciones: npx prisma migrate dev
```

### 4.4 Ejecutar
```bash
pnpm dev
# → http://localhost:3000
```

## 5. Verificar Instalación

### Prueba 1: Flask corre
```bash
curl http://localhost:5000/planes
# → HTML de la página de planes
```

### Prueba 2: Next.js corre
```bash
curl http://localhost:3000/api/test
# → {"test":"API is working","time":"..."}
```

### Prueba 3: DB conectada
```bash
python test_db.py
# → Debe mostrar conexión exitosa + tablas encontradas
```

### Prueba 4: Auth integrada
1. Abrir `http://localhost:3000`
2. Click "Comenzar" → debe redirigir a Flask `/register`
3. Registrar restaurante → debe redirigir a Next.js `/flask-auth`
4. Verificar email → dashboard de Scanner IA

---

## Scripts Útiles

### Ordenfox (Flask)
```bash
.\.venv\Scripts\Activate.ps1
python run.py                  # Dev server
flask db migrate -m "msg"     # Nueva migración
flask db upgrade              # Aplicar migraciones
flask cleanup-accounts        # Limpiar cuentas inactivas
python test_db.py              # Test conexión DB
npm run build:css              # Build Tailwind prod
npm run watch:css              # Watch Tailwind dev
```

### Scanner IA (Next.js)
```bash
pnpm dev                       # Dev server
pnpm build                     # Build producción
pnpm lint                      # ESLint
npx prisma studio              # Prisma UI (DB browser)
node scripts/diagnose.js       # Diagnóstico DB
```

---

## Solución de Problemas Comunes

### ❌ MySQL connection fails
```bash
# Verificar que MySQL está corriendo
net start MySQL80

# Verificar URL correcta
# Usa mysql+pymysql:// NO mysql://
```

### ❌ Clerk auth no funciona
```bash
# Verificar que las keys son las mismas en Flask y Next.js
# Clerk JWT Issuer debe coincidir con el dominio de Clerk
```

### ❌ Next.js no encuentra usuario en DB
```bash
# Si ves "Cuenta no encontrada" en /dashboard:
# 1. El usuario existe en Clerk pero no en MySQL
# 2. Registrar via Flask primero, o crear manualmente
```

### ❌ Recarga de tokens no funciona
```bash
# Verificar SERVICE_API_KEY igual en ambos proyectos
# Verificar ORDERFOX_URL apunta a Flask
# Verificar que Flask tiene MP_ACCESS_TOKEN configurado
```

### ❌ OCR/DeepSeek falla
```bash
# Verificar GOOGLE_VISION_API_KEY
# Verificar DEEPSEEK_API_KEY
# Revisar consola Next.js para errores específicos
# El sistema reembolsa el token automáticamente si falla
```

---

## Arquitectura de URLs

```
localhost:5000/                  → Flask (Orderfox) — Dashboard web
localhost:3000/                  → Next.js (Scanner IA) — Landing + Dashboard gastos
localhost:5000/register          → Flask — Registro de restaurante
localhost:5000/menu/<slug>       → Flask — Menú público (QR)
localhost:5000/dashboard         → Flask — Panel de control pedidos
localhost:3000/dashboard          → Next.js — Panel de gastos
localhost:5000/api/*             → Flask — API REST
localhost:3000/api/*              → Next.js — API REST
```

---

*Documento mantenido en /docs/QUICK_START.md*
