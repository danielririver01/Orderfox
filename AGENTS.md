# Orderfox AI Agent Instructions

**Orderfox** (v1.3.0) is a **multi-tenant SaaS restaurant ordering platform** enabling food businesses to manage digital menus via QR codes, track real-time orders, and handle subscriptions with tiered AI features.

## Quick Start

```bash
# Setup
.\.venv\Scripts\Activate.ps1          # Windows activation
pip install -r requirements.txt        # Backend dependencies
npm install                            # Frontend dependencies

# Development
python run.py                          # Flask dev server (localhost:5000)
npm run watch:css                      # Watch Tailwind CSS changes

# Database
flask db migrate -m "description"      # Create migration after model changes
flask db upgrade                       # Apply migrations
python test_db.py                      # Debug database state
```

**Required Environment Variables:** `SECRET_KEY`, `DATABASE_URL` (MySQL), `CLERK_SECRET_KEY`, `CLOUDINARY_*`, `MP_ACCESS_TOKEN` (Mercado Pago), `SCANNER_IA_URL` — see [settings.py](settings.py).

---

## Architecture

**Type:** Monolithic Flask app serving both web pages (Jinja2 templates) and RESTful APIs. Multi-tenant isolation via `restaurant_id` foreign key.

**Stack:**
- **Backend:** Flask 3.x + SQLAlchemy ORM
- **Database:** MySQL 8.x
- **Frontend:** Tailwind CSS 4.2.4 + Vanilla JavaScript (no framework)
- **Auth:** Clerk (OAuth) + JWT for APIs
- **Storage:** Cloudinary CDN
- **Payments:** Mercado Pago API
- **Jobs:** APScheduler (daily cleanup, order expiry)
- **PWA:** Workbox 7.4.1 (offline caching)

**Directory Structure:**
```
app/
├── routes/          # Web pages (dashboard, auth, public menu)
├── api_*.py         # JSON endpoints (/api/auth, /api/orders, etc.)
├── models.py        # 12+ SQLAlchemy models
├── tasks.py         # Scheduled jobs
├── extensions.py    # Flask extensions
├── utils/           # Helpers (subscription, auth, rate_limiting)
├── static/          # CSS, JS, uploads
└── template/        # Jinja2 templates (dashboard, auth, email)
```

---

## Critical Conventions (Non-Negotiable)

### 1. **UTC Timestamps Everywhere**

⚠️ **ENFORCEMENT LEVEL: CRITICAL** — This is a common source of bugs.

- ✅ **DO:** `datetime.now(timezone.utc)` for all timestamps
- ✅ **DO:** Use SQLAlchemy's `AwareDateTime` type for model columns
- ❌ **DON'T:** `datetime.now()` without UTC
- ❌ **DON'T:** Calculate dates/times in frontend JavaScript

**Implementation:** Custom `AwareDateTime` SQLAlchemy type automatically converts UTC to/from MySQL. Frontend receives ISO 8601 strings; backend does all calculations.

**Read:** [docs/TIMEZONE_HANDLING.md](docs/TIMEZONE_HANDLING.md) for verification patterns and edge cases.

---

### 2. **Backend Calculates Everything (Client Cannot Be Trusted)**

| Category | Examples | Who Handles It |
|----------|----------|---|
| **Subscription Status** | Expiry dates, grace periods, token balance | Backend only |
| **Rate Limiting** | Spam detection, punishment timeouts | Backend only |
| **Authentication** | User verification, permission checks | Backend only |
| **Business Logic** | Order validity, pricing, discounts | Backend only |

**Pattern:** Frontend sends minimal data → Backend validates & computes → API response includes result state.

**Example:** Frontend doesn't check if subscription is expired—backend computes `get_subscription_status(restaurant)` and returns `{ status: "active" | "expiring_soon" | "grace_period" | "expired" }`.

---

### 3. **Database as Single Source of Truth (No Implicit User Creation)**

**Authentication Policy:** User must exist in both Clerk AND database.

- ✅ User logs in via Clerk → Backend checks MySQL `User` table
- ❌ If in Clerk but NOT in database → **Automatic logout**
- ❌ Never auto-create database users from Clerk tokens

**Error Flow:**
```python
# Pseudo-code
user = db.session.query(User).filter_by(clerk_id=clerk_user_id).first()
if not user:
    return {"success": False, "error_code": "USER_NOT_REGISTERED", 
            "message": "Debe registrarse en la plataforma para poder acceder."}
```

**Read:** [/memories/repo/authentication-policy.md](/memories/repo/authentication-policy.md)

---

### 4. **Smart Rate Limiting (Not Blanket Blocking)**

**Smart Detection Algorithm:**
- **Normal usage:** 12-second cooldown between orders
- **Spam pattern detected** (3+ failed orders in 2 minutes): 30-second punishment
- **Exemption:** Requests with `x-api-key` header (Scanner IA service) bypass limits

**Don't implement naive blanket timeouts.** See [docs/RATE_LIMITING_INTEL.md](docs/RATE_LIMITING_INTEL.md) for full algorithm and rationale.

---

### 5. **API Response Format (Standardized)**

All JSON responses follow this schema:

```json
// Success
{ "success": true, "message": "Order created", "data": { "order_id": 123 } }

// Error
{ "success": false, "error_code": "USER_NOT_REGISTERED", "message": "..." }
```

---

### 6. **Multi-Tenant Isolation (Via restaurant_id FK)**

Every model that belongs to a restaurant has `restaurant_id` foreign key.

- ✅ **DO:** Always filter by `restaurant_id` when querying
- ❌ **DON'T:** Assume user owns the restaurant (validate via `current_user.restaurant_id`)

**Example:**
```python
# ✅ Correct: Verify user's restaurant
restaurant = db.session.query(Restaurant).filter_by(
    id=restaurant_id, owner_id=current_user.id
).first()
if not restaurant:
    abort(403, "Unauthorized")
```

---

### 7. **CSRF Protection (Web Routes Only)**

- ✅ **Web routes** (`routes/`) require CSRF token: `{{ csrf_token() }}` in forms
- ❌ **API routes** (`api_*.py`) are exempt from CSRF (use JWT/API keys)

---

## Common Gotchas & Solutions

| Issue | Fix |
|-------|-----|
| **Timezone bugs** | Use UTC everywhere; backend only; see [TIMEZONE_HANDLING.md](docs/TIMEZONE_HANDLING.md) |
| **User not found after login** | Implement USER_NOT_REGISTERED check; see [authentication-policy.md](/memories/repo/authentication-policy.md) |
| **Legitimate users rate-limited** | Switch to smart detection algorithm; see [RATE_LIMITING_INTEL.md](docs/RATE_LIMITING_INTEL.md) |
| **MySQL connection fails silently** | Always set `DATABASE_URL` env var |
| **Static files 404 in dev** | Flask debug mode handles them automatically |
| **File upload fails** | Check `MAX_CONTENT_LENGTH` in settings.py (default 16 MB) |
| **Trial logic breaks** | Trial duration hard-coded in `models.py` → `TrialHistory` |
| **Email fails** | Gmail requires app-specific password in `MAIL_PASSWORD` |
| **Scanner IA doesn't work** | Verify `SERVICE_API_KEY` env var matches exactly |

---

## Key Files to Know

| File | Purpose |
|------|---------|
| [settings.py](settings.py) | All environment configuration |
| [app/models.py](app/models.py) | 12+ SQLAlchemy models (Restaurant, Order, User, etc.) |
| [app/utils/subscription.py](app/utils/subscription.py) | Subscription status calculation logic |
| [app/utils/rate_limiter.py](app/utils/rate_limiter.py) | Smart rate limiting implementation |
| [docs/TIMEZONE_HANDLING.md](docs/TIMEZONE_HANDLING.md) | UTC conversion patterns |
| [docs/RATE_LIMITING_INTEL.md](docs/RATE_LIMITING_INTEL.md) | Spam detection algorithm |

---

## Reserved URL Slugs

These cannot be used as restaurant names (they conflict with system routes):
`scanner-ia`, `admin`, `api`, `dashboard`, `auth`, `static`, `public`, `menu`, `health` — see [app/routes/auth.py](app/routes/auth.py) for full list.

---

## Before You Code

1. ✅ Understand UTC is non-negotiable (verify with [TIMEZONE_HANDLING.md](docs/TIMEZONE_HANDLING.md))
2. ✅ Backend computes all business logic; frontend is presentation only
3. ✅ User must exist in both Clerk AND database (implement USER_NOT_REGISTERED)
4. ✅ Always filter queries by `restaurant_id` to prevent data leakage
5. ✅ Use smart rate limiting, not naive timeouts
6. ✅ Follow standardized API response format
7. ✅ Check CSRF requirements for route type (web vs. API)

---

**Questions?** Refer to [/memories/repo/orderfox-codebase-guide.md](/memories/repo/orderfox-codebase-guide.md) for deeper architectural details, or ask a follow-up question.
