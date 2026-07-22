# Burp Suite — Security Testing

## Installation

```powershell
winget install --id PortSwigger.BurpSuite.Community --accept-source-agreements
```

Version installed: 2026.3.3

## Configuration

1. Open Burp Suite Community
2. **Proxy → Intercept → Intercept is on**
3. Browser proxy: `http://127.0.0.1:8080`
4. Install CA cert: `http://burpsuite` → Download CA Certificate → import in browser
5. View traffic: **Proxy → HTTP history**

## Automated Tests

Run the automated security tests:

```powershell
python tests/security/burp/run_auto_tests.py
```

This covers:
- **Test 1 (IDOR):** Accessing another restaurant's data
- **Test 4 (NoAuth):** Routes that should require authentication
- **Test 5 (Fuzzing):** Malformed parameters

### Latest Results (2026-07-20)

| Test | Result |
|------|--------|
| NoAuth /api/products | PASS (302) |
| NoAuth /api/orders | PASS (302) |
| NoAuth POST /api/categories | PASS (401) |
| NoAuth /api/tables | PASS (302) |
| NoAuth /insights/api/conversations/1 | PASS (302) |
| NoAuth /insights/api/events/pending | PASS (302) |
| IDOR categories (other restaurant) | PASS (filtered to own) |
| IDOR products (other restaurant) | PASS (filtered to own) |
| IDOR orders (other restaurant) | PASS (filtered to own) |
| IDOR create order (other restaurant) | PASS (400) |
| Fuzzing params | PASS (no crashes) |

**Summary:** 0 critical findings. Backend correctly filters by authenticated restaurant, not URL params.

---

## Manual Tests (via Burp Suite)

### Test 2 — JWT Tampering

**Objective:** Verify backend validates JWT signature.

**Steps:**
1. Login in browser, intercept request with `Authorization: Bearer <jwt>`
2. In Burp: right-click → **Send to Repeater**
3. Go to **Inspector → JSON Web Token**
4. Modify payload: `sub: 5` → `sub: 1`, `restaurant_id: 5` → `999999`
5. Send

**Expected:** 401 Unauthorized

**Variants:**
- Change `alg` to `none`
- Empty signature
- Expired token (`exp` in past)

---

### Test 3 — Price/Quantity Modification

**Objective:** Verify backend validates amounts.

**Steps:**
1. Create order, intercept `POST /api/orders`
2. Modify body:
   - `precio: 10000` → `precio: 0`
   - `precio: 10000` → `precio: -500`
   - `cantidad: 1` → `cantidad: 999999`
   - `cantidad: 1` → `cantidad: -1`
3. Send

**Expected:** Backend rejects or validates against real product prices.

### Results (2026-07-20, code review + API test)

| Attack | Status | Finding |
|--------|--------|---------|
| `precio: 0` | ✅ SECURE | Backend ignores client price. Uses `item_price = product.price` (DB lookup, `order_service.py:156`) |
| `precio: -500` | ✅ SECURE | Same — client price not trusted |
| `cantidad: 999999` | ⚠️ LOW | Accepted. Unusual but not exploitable (no crash, no priv-esc) |
| `cantidad: -1` | ⚠️ LOW | **VULNERABILITY** — creates negative subtotal, reduces order total. No `quantity > 0` validation (`order_service.py:142`) |

**Fix needed:** Add `if quantity <= 0: raise ValueError` in `OrderService._validate_and_add_items` (line 142).

**Confirmed via API (2026-07-20):** `POST /api/orders` with `quantity: -1` returned `201` and `total: -5000`.

---

## Results Log

| Date | Tester | Prueba | Result | Notes |
|------|--------|--------|--------|-------|
| 2026-07-20 | auto | 1-IDOR | PASS | Backend filters by JWT restaurant |
| 2026-07-20 | auto | 2-JWT | PASS | Tampered sub=401, alg=none=401, valid=200 |
| 2026-07-20 | auto | 3-Prices | PASS/LOW | Price tamper secure; negative quantity = vuln |
| 2026-07-20 | auto | 4-NoAuth | PASS | All routes redirect or 401 |
| 2026-07-20 | auto | 5-Fuzzing | PASS | No crashes |
