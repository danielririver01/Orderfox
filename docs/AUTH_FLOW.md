# Flujo de Autenticación — Velzia

> **Componentes:** Clerk OAuth + Flask Session + JWT + API Key

## Diagrama General

```mermaid
graph TD
    subgraph "Métodos de Autenticación"
        W[Web Browser] -->|Session Cookie| S[Flask Session]
        M[Mobile/API] -->|JWT Bearer| J[JWT Auth]
        N[Scanner IA] -->|Clerk Session| C[Clerk]
        S2[Server-to-Server] -->|x-api-key| K[API Key]
    end

    subgraph "Flask Decorators"
        S --> L[login_required]
        J --> JL[jwt_login_required]
        K --> KT[/api/tokens/* bypass]
    end

    L --> A[active_required]
    JL --> JA[jwt_active_required]
    A --> F[feature_required]
    JA --> JF[jwt_feature_required]
    
    L & J --> FL[flexible_login_required<br/>accepts both]
```

## 1. Web (Session) — Login Tradicional

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant Flask
    participant DB
    participant Clerk

    User->>Browser: / (login page)
    Browser->>Flask: POST / (email + password)
    Flask->>DB: AuthService.authenticate()
    DB-->>Flask: User or None
    alt success
        Flask->>Flask: session['user_id'] = user.id
        Flask-->>Browser: Redirect /dashboard
    else fail
        Flask-->>Browser: Flash error, recarga login
    end

    Note over Browser,Flask: Clerk OAuth Sync
    User->>Clerk: Inicia sesión con Google/GitHub
    Clerk-->>Browser: Clerk Session Token
    Browser->>Flask: POST /api/sync-clerk (Clerk session)
    Flask->>Clerk: Verify session via Clerk API
    Clerk-->>Flask: { email, username }
    Flask->>DB: AuthService.sync_or_create_user()
    Flask-->>Browser: { success, redirect_url }
    Browser->>Flask: GET /dashboard
```

## 2. API (JWT) — Login Mobile

```mermaid
sequenceDiagram
    actor Client
    participant API
    participant Flask
    participant DB
    participant Clerk

    Client->>Flask: POST /api/auth/login (email, password)
    Flask->>DB: AuthService.api_login()
    DB-->>Flask: User
    Flask-->>Client: { access_token, refresh_token, user, restaurant }

    Note over Client,Flask: Access token: 15 min
    Note over Client,Flask: Refresh token: 30 days

    Client->>Flask: GET /api/dashboard/overview (JWT Bearer)
    Flask->>Flask: jwt_login_required → verify JWT
    Flask-->>Client: JSON response

    Note over Client,Flask: Token Refresh
    Client->>Flask: POST /api/auth/refresh (refresh_token)
    Flask-->>Client: { access_token }

    Note over Client,Flask: API Register Flow
    Client->>Flask: POST /api/auth/register (email, plan_type)
    Flask->>Flask: AuthService.api_register()
    Flask-->>Client: { temp_token } (JWT with OTP embedded)
    Flask->>Email: Send OTP code
    
    Client->>Flask: POST /api/auth/verify-otp (temp_token, otp)
    Flask->>Flask: AuthService.verify_otp()
    Flask-->>Client: { verified_token }
    
    Client->>Flask: POST /api/auth/setup-account (verified_token, data)
    Flask->>DB: AuthService.api_setup_account()
    Flask-->>Client: { access_token, refresh_token, user, restaurant }
```

## 3. Scanner IA — Clerk + Flask Bridge

```mermaid
sequenceDiagram
    actor User
    participant NextJS as Scanner IA
    participant Clerk
    participant Flask
    participant DB

    Note over User,DB: Registro
    User->>NextJS: /sign-up
    NextJS->>User: Redirect /register?plan=trial
    User->>Flask: Register form
    Flask->>DB: Crea Restaurant + User + TokenWallet
    Flask-->>User: Redirect /flask-auth?flask_token=JWT
    
    User->>NextJS: /flask-auth?flask_token=xxx
    NextJS->>NextJS: Verify JWT with FLASK_SECRET_KEY
    NextJS->>Clerk: signIn.create({ strategy: "email_code", email })
    Clerk->>User: Email con código
    User->>NextJS: /sign-in (ingresa código)
    NextJS->>Clerk: Verify code
    Clerk->>NextJS: Session created
    NextJS->>User: Redirect /dashboard

    Note over User,DB: Dashboard Access
    User->>NextJS: /dashboard
    NextJS->>Clerk: auth() → userId
    NextJS->>DB: Prisma: find user by clerk_id
    DB-->>NextJS: User data
    NextJS->>User: Dashboard page

    Note over User,DB: AI Scan
    User->>Flask: GET /dashboard/ai-scan
    Flask->>Flask: Genera JWT firmado (5 min expiry)
    Flask->>User: Redirect to Next.js + JWT in URL
    User->>NextJS: /dashboard + JWT query param
    NextJS->>Flask: GET /api/auth/verify (JWT)
    Flask-->>NextJS: { clerk_id, email }
    NextJS->>Clerk: Sign in user
    Note over User,NextJS: User authenticated in Next.js
```

## 4. Server-to-Server (API Key)

```mermaid
sequenceDiagram
    participant Ext as Servicio Externo
    participant Flask

    Ext->>Flask: POST /api/tokens/consume
    Note over Ext: Header: x-api-key: <SERVICE_API_KEY>
    Flask->>Flask: exempt_from_limiter() → True
    Flask->>Flask: TokenService.consume_token()
    Flask-->>Ext: { success, tokens_remaining }
```

## 5. Decoradores — Referencia Rápida

| Decorador | Auth | Uso | Respuesta si falla |
|-----------|------|-----|-------------------|
| `@login_required` | Session | Web routes | Redirect a `/` o JSON 401 |
| `@active_required` | Session | Verifica restaurante activo + suscripción | Flash error o JSON 403 |
| `@feature_required('feature')` | Session | Verifica feature del plan | Flash o JSON 403 |
| `@jwt_login_required` | JWT | API routes | JSON 401 |
| `@jwt_active_required` | JWT | API: verifica activo + suscripción | JSON 403 |
| `@jwt_feature_required('feature')` | JWT | API: verifica feature del plan | JSON 403 |
| `@flexible_login_required` | JWT o Session | API categories (dual) | JSON 401 |
| `@flexible_active_required` | JWT o Session | API: activo + suscripción | JSON 403 |

### Orden de aplicación correcta:
```python
# Web
@login_required
@active_required
@feature_required('has_modifiers')
def create_modifier(): ...

# API
@jwt_login_required
@jwt_active_required
@jwt_feature_required('has_table_qr')
def create_table(): ...
```

## 6. JWT Structure

### Access Token (15 min)
```json
{
  "sub": "<user_id>",
  "restaurant_id": "<int>",
  "clerk_id": "<string>",
  "type": "access",
  "iat": 1234567890,
  "exp": 1234568790
}
```

### Refresh Token (30 days)
```json
{
  "sub": "<user_id>",
  "type": "refresh",
  "jti": "<uuid>",
  "iat": 1234567890,
  "exp": 1234567890 + 30d
}
```

### Flask → Next.js Bridge Token (5 min)
```json
{
  "clerk_id": "<string>",
  "user_id": "<int>",
  "email": "<email>",
  "type": "flask_auth",
  "iat": 1234567890,
  "exp": 1234567890 + 300
}
```

## 7. CSRF Protection

| Tipo de Ruta | CSRF | Método |
|-------------|------|--------|
| Web forms (`/dashboard/*`, `/categories/*`, etc.) | ✅ Requerido | Token via `{{ csrf_token() }}` |
| API routes (`/api/*`) | ❌ Exento | `before_request` hook |
| Webhooks (`/webhook`) | ❌ Exento | `@csrf.exempt` |
| Token consume/topup | ❌ Exento | `@csrf.exempt` |

---

*Documento mantenido en /docs/AUTH_FLOW.md*
