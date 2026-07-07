# Orderfox AI Agent Guide

**Project:** Restaurant ordering management SaaS platform  
**Version:** 1.3.0 | **Stack:** Flask (Python) + Vanilla JS + Tailwind CSS + MySQL  
**Repository:** https://github.com/danielririver01/Orderfox.git

---

## Quick Start Commands

```bash
# Activate virtual environment (Windows)
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
npm install

# Run Flask dev server (http://localhost:5000)
python run.py

# Watch Tailwind CSS changes
npm run watch:css

# Build Tailwind CSS (production)
npm run build:css

# Database migrations
flask db migrate -m "description"
flask db upgrade

# Debug tools
python test_db.py        # Check database state
python rescues_db.py     # Rescue specific data
```

---

## Architecture Overview

**Monolithic Full-Stack** — Single Flask app serving both:
- **Web pages** (restaurant dashboard, auth flows)
- **RESTful JSON APIs** (Scanner IA integration, mobile clients)

### Component Breakdown

```
app/
  ├── routes/              # Web blueprints (render HTML pages)
  ├── routes/api_*.py      # REST API endpoints (JSON responses)
  ├── models.py            # SQLAlchemy ORM (Restaurant, User, Order, etc.)
  ├── extensions.py        # Flask extensions (Mail, JWT, Limiter, etc.)
  ├── forms/               # WTForms for validation
  ├── utils/               # Helpers (auth, subscription, rate-limiting)
  ├── tasks.py             # APScheduler jobs (cleanup, expiry)
  ├── csrf.py              # CSRF token management
  └── static/
      ├── CSS/             # Tailwind (input.css → output.css)
      ├── js/              # Vanilla JS modules
      └── uploads/         # User-uploaded assets cache

template/                  # Jinja2 HTML templates
  ├── common/              # Base layouts
  ├── dashboard/           # Owner dashboard views
  ├── public/              # Customer-facing (QR order page)
  └── auth/                # Login, register, recovery

migrations/                # Alembic database versions
docs/                      # Project documentation
```

---

## Key Conventions & Patterns

### 1. **Database Timezone Handling** ⏰ *Critical*

**Rule:** ALL dates stored/compared in UTC only.

- **Always use:** `datetime.now(timezone.utc)` (never `datetime.now()`)
- **Implementation:** `AwareDateTime` type decorator in models strips timezone on write, adds it back on read
- **Impact:** Subscription expiry, order timers, all backend calculations must use UTC
- **Reference:** [docs/02-GUIDES/GUIDE-01_Timezone_Handling.md](docs/02-GUIDES/GUIDE-01_Timezone_Handling.md)

```python
# ✅ Correct
from datetime import datetime, timezone
expires = datetime.now(timezone.utc) + timedelta(days=7)

# ❌ Wrong (naïve datetime)
expires = datetime.now() + timedelta(days=7)
```

### 2. **Authentication Policy** 🔐

**Database is source of truth.** If user is in Clerk but NOT in DB → auto-create with trial plan.

- New users get 10-day trial + 10 AI tokens automatically
- No implicit user creation without database record
- Error code for rejected access: `USER_NOT_REGISTERED`
- **Reference:** [docs/TIMEZONE_HANDLING.md](docs/TIMEZONE_HANDLING.md)

### 3. **Subscription State** 💳

**Single source of truth:** Backend-only calculation via `get_subscription_status(restaurant)`

- Returns: `is_active`, `status`, `message`, `badge_class`, `can_crud`
- **Never** do frontend date math
- States: `active` → `trial` → `grace_period` → `expired`
- **Frontend receives pre-computed object**
- **Reference:** [docs/02-GUIDES/GUIDE-01_Timezone_Handling.md](docs/02-GUIDES/GUIDE-01_Timezone_Handling.md)

### 4. **Rate Limiting** 🚨 Intelligent

- **Max:** 3 orders per minute per IP
- **Ban:** 10 minutes if limit exceeded
- **Honeypot:** Hidden field in order form traps bots
- **Time-to-submit:** Minimum 3 seconds between checkout start and order
- **Exemption:** `SERVICE_API_KEY` header (server-to-server)
- **Reference:** [docs/02-GUIDES/GUIDE-02_Rate_Limiting.md](docs/02-GUIDES/GUIDE-02_Rate_Limiting.md)

### 5. **API Response Format** 📨

All JSON responses follow this structure:

```json
{
  "success": true,
  "message": "Operación exitosa",
  "data": { /* payload */ }
}
```

Error responses:
```json
{
  "success": false,
  "error_code": "ERROR_CODE",
  "message": "Human-readable message in Spanish"
}
```

### 6. **CSRF Protection** 🛡️

- **API routes** (`/api/*`): Exempt from CSRF (use JWT or API key)
- **Web forms**: Must include CSRF token via `{{ csrf_token() }}`
- **Default:** POST/PUT/DELETE require CSRF unless exempted

### 7. **Naming Conventions** 📝

| Type | Convention | Example |
|------|-----------|---------|
| Database | `snake_case` | `subscription_expires_at` |
| URLs | `kebab-case` | `/api/products/list` |
| JS functions | `camelCase` | `updateQty()`, `calculateTotal()` |
| CSS classes | Tailwind + custom | `btn-primary`, `card` |

---

## Task Scheduling (APScheduler)

Jobs in `/app/tasks.py`:

1. **Daily 3:00 AM** — `delete_inactive_accounts()`
   - Removes restaurants marked inactive 24+ hours
   - Cascades: deletes users, orders, products

2. **Hourly** — `expire_pending_orders()`
   - Marks orders as 'expired' if past `expires_at`
   - Default expiry: 24 hours (configurable)

---

## Common Development Tasks

| Task | Files | Command |
|------|-------|---------|
| Add API endpoint | `/app/routes/api_*.py` | Create blueprint or extend existing |
| Add form field | `/app/forms/*.py` + `models.py` | Update model, then `flask db migrate` |
| Schedule job | `/app/tasks.py` | Register in `create_app()` |
| Add database table | `/app/models.py` | `flask db migrate` → `flask db upgrade` |
| Update CSS | `/app/static/CSS/src/input.css` | `npm run build:css` (or watch) |
| Add JS module | `/app/static/js/` | Reference in template `<script>` tag |
| Modify template | `/app/template/` | Corresponding `.html` file |
| Fix auth issue | `/app/routes/auth.py` + `/app/template/auth/` | Check Clerk sync + DB |
| Tune rate limiter | `/app/utils/rate_limiter.py` | See docs for thresholds |

---

## Environment Variables (Required)

See `settings.py` for full list. Key ones:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Session/CSRF encryption |
| `DATABASE_URL` | MySQL connection (default: `mysql+pymysql://root:@localhost/orderfox`) |
| `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD` | Email via Gmail SMTP |
| `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | OAuth provider |
| `CLOUDINARY_*` | Image hosting |
| `MP_ACCESS_TOKEN`, `MP_PUBLIC_KEY` | Mercado Pago payments |
| `SCANNER_IA_URL`, `SERVICE_API_KEY` | External AI service |
| `BASE_URL` | For QR generation (ngrok/production domain) |

---

## Common Gotchas ⚠️

### 1. **MySQL Connection Fails Silently**
```
❌ mysql://user:password@host/database    (wrong driver)
✅ mysql+pymysql://user:password@host/database
```

### 2. **Trial Period Hard-Coded**
- 10 days, not configurable per request
- Stored in `TrialHistory` table
- Grace period after expiry: 10 days (users can't create/edit content)

### 3. **Static Files in Production**
- WhiteNoise serves `app/static/` as `/static/`
- **Must pre-build** CSS: `npm run build:css`
- No dynamic CSS generation in production

### 4. **Timezone Testing**
- Create test orders and check `expires_at` in MySQL directly
- Use `datetime.now(timezone.utc)` when debugging

### 5. **Gmail Email Configuration**
- Requires **app-specific password**, not your account password
- TLS enabled by default
- `MAIL_USERNAME` used as "From" address unless `MAIL_DEFAULT_SENDER` set

### 6. **Rate Limiter Storage**
- In-memory only (resets on restart)
- For multi-process/distributed: consider Redis

### 7. **File Upload Max Size**
- 16 MB (configured in `MAX_CONTENT_LENGTH`)
- Uploaded to Cloudinary; local cache in `app/static/uploads/`
- Old files not auto-deleted; manual cleanup needed

### 8. **Reserved Slugs**
- Cannot create restaurants with slugs like `api`, `admin`, `auth`, etc.
- See `RESERVED_SLUGS` in `/app/routes/auth.py`

---

## API Authentication

| Type | Header | Use Case |
|------|--------|----------|
| **Service API Key** | `x-api-key: <key>` | Server-to-server (Scanner IA) — **bypasses rate limiting** |
| **JWT** | `Authorization: Bearer <token>` | Mobile/external clients — 24-hour expiry |
| **Clerk Session** | Cookie-based | Web browsers — OAuth redirect |

---

## URL Patterns

```
/                              # Landing/login
/dashboard/                    # Owner dashboard (protected)
/dashboard/products            # Product management
/dashboard/categories          # Category management
/dashboard/orders              # Order list
/dashboard/subscription        # Billing & subscription status
/{restaurant_slug}/menu        # Public customer menu (QR target)
/{restaurant_slug}/order/{id}  # Order status page

/api/auth/login               # Login endpoint
/api/auth/sync-clerk          # Clerk OAuth sync
/api/products/list            # JSON API
/api/orders/create            # Create order via API
```

---

## Deployment Notes

- **Server:** Gunicorn or similar WSGI server required
- **Static files:** Run `npm run build:css` before deploying
- **Migrations:** Run `flask db upgrade` after code deployment
- **Secrets:** Via `.env` (not in version control)
- **Database:** MySQL 8.x with UTF-8MB4 support
- **Scheduled tasks:** APScheduler requires app instance; consider Celery for distributed jobs

---

## Related Documentation

- [Rate Limiting System Design](docs/RATE_LIMITING_INTEL.md) — Spam detection algorithm
- [Timezone Handling Strategy](docs/TIMEZONE_HANDLING.md) — UTC philosophy & implementation
- [SWOT Analysis](docs/DOFA.md) — Business strengths, weaknesses, opportunities, threats

---

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| **Backend Framework** | Flask 3.x |
| **Database** | MySQL 8.x + SQLAlchemy ORM |
| **Migrations** | Alembic + Flask-Migrate |
| **Authentication** | Clerk OAuth + JWT |
| **Email** | Flask-Mail (Gmail SMTP) |
| **File Storage** | Cloudinary CDN |
| **Payments** | Mercado Pago API |
| **Rate Limiting** | Flask-Limiter (intelligent) |
| **Job Scheduling** | APScheduler |
| **Frontend CSS** | Tailwind CSS 4.2.4 |
| **Templating** | Jinja2 |
| **JavaScript** | Vanilla (no framework) |

---

## Quick Reference: Data Models

- **Restaurant** — Tenant (unique per business)
- **User** — Staff/owner (linked to Restaurant)
- **Product** — Menu items
- **Category** — Product grouping
- **Modifier** — Product extras (toppings, sizes, etc.)
- **Order** — Customer orders
- **OrderItem** — Items in an order
- **Table** — Physical tables (dine-in)
- **TrialHistory** — Trial eligibility tracking (email + phone)
- **AITokenWallet** — User's AI token balance
- **AITokenTransaction** — Token consumption log

---

Generated by Copilot Agent Customization | *Last updated: 2026-06-16*
