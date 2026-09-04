"""
reset_felicia_demo.py — Mantenimiento demo (restaurant_id=1, "Felicia").

Fases (ejecutar en orden, cada una verificable):
    backup   → vuelca categorías/tablas/productos/órdenes a JSON en backups/
    wipe     → borra productos y órdenes de R1 (cascada a items/events/modifiers).
               Conserva categorías y mesas.
    recreate → recrea los MISMOS productos (desde el backup) vía ProductService
               y ejecuta el pipeline AutoPhoto (LATAM library / Unsplash).
    seed     → genera ventas de agosto 2026 (día 1..31) con los productos nuevos.
    report   → resumen: fotos duplicadas + ventas de agosto por día/método.

Seguridad:
    - `wipe` solo corre si existe un backup reciente del mismo día.
    - Todos los borrados son por restaurant_id=1.
    - Fechas: se guardan en UTC (naive); las locales de Colombia (UTC-5) se
      convierten con COLOMBIA_TZ antes de persistir.

Uso:
    .venv/Scripts/python scripts/reset_felicia_demo.py <fase>
"""

import sys
import os
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Permitir ejecución directa: python scripts/reset_felicia_demo.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Console Windows: UTF-8 para nombres con tildes/ñ sin romper el pipe
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RESTAURANT_ID = 1
BACKUP_ROOT = Path("backups")
BACKUP_LABEL = "felicia_reset_2026-09-03"

from app import create_app
from app.models import db, Product, Order, OrderItem, OrderCounter, Category, Table, Modifier
from app.services.product_service import ProductService
from app.services.auto_photo_service import AutoPhotoService
from app.utils import latam_photo_library
from app.utils.timezone import COLOMBIA_TZ

random.seed(20260903)  # reproducible


# ─────────────────────────────────────────────────────────────
# Backup
# ─────────────────────────────────────────────────────────────
def _dump_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


def phase_backup():
    print("[backup] Snapshot restaurante", RESTAURANT_ID)
    out_dir = BACKUP_ROOT / BACKUP_LABEL
    out_dir.mkdir(parents=True, exist_ok=True)

    def rows(sql, params=None):
        res = db.session.execute(db.text(sql), params or {})
        cols = list(res.keys())
        return [dict(zip(cols, r)) for r in res.fetchall()]

    categories = rows(
        "SELECT * FROM categories WHERE restaurant_id=:r ORDER BY id", {"r": RESTAURANT_ID}
    )
    tables = rows(
        "SELECT * FROM tables WHERE restaurant_id=:r ORDER BY id", {"r": RESTAURANT_ID}
    )
    modifiers = rows(
        "SELECT * FROM modifiers WHERE restaurant_id=:r ORDER BY id", {"r": RESTAURANT_ID}
    )
    products = rows(
        "SELECT * FROM products WHERE restaurant_id=:r ORDER BY id", {"r": RESTAURANT_ID}
    )
    orders = rows(
        "SELECT * FROM orders WHERE restaurant_id=:r ORDER BY id", {"r": RESTAURANT_ID}
    )
    order_items = rows(
        "SELECT * FROM order_items WHERE restaurant_id=:r ORDER BY id", {"r": RESTAURANT_ID}
    )
    order_events = rows(
        "SELECT * FROM order_events WHERE order_id IN "
        "(SELECT id FROM orders WHERE restaurant_id=:r) ORDER BY id",
        {"r": RESTAURANT_ID},
    )
    counters = rows(
        "SELECT * FROM order_counters WHERE restaurant_id=:r ORDER BY date", {"r": RESTAURANT_ID}
    )

    payload = {
        "restaurant_id": RESTAURANT_ID,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "categories": categories,
        "tables": tables,
        "products": products,
        "modifiers": modifiers,
        "orders": orders,
        "order_items": order_items,
        "order_events": order_events,
        "order_counters": counters,
    }
    fname = out_dir / "snapshot.json"
    fname.write_text(_dump_json(payload), encoding="utf-8")

    print(f"  -> {fname} ({fname.stat().st_size/1024:.1f} KB)")
    print(f"     categories={len(categories)} tables={len(tables)} "
          f"products={len(products)} modifiers={len(modifiers)}")
    print(f"     orders={len(orders)} items={len(order_items)} events={len(order_events)} "
          f"counters={len(counters)}")


def _load_snapshot():
    fname = BACKUP_ROOT / BACKUP_LABEL / "snapshot.json"
    if not fname.exists():
        sys.exit(f"[error] No existe backup: {fname}. Corre 'backup' primero.")
    with open(fname, encoding="utf-8") as fh:
        return json.load(fh)


# ─────────────────────────────────────────────────────────────
# Wipe
# ─────────────────────────────────────────────────────────────
def phase_wipe():
    snap = _load_snapshot()
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    exported = snap.get("exported_at", "")[:10]
    if exported != today:
        sys.exit(
            f"[error] El backup es del {exported}, no de hoy ({today}). "
            "Genera un backup nuevo antes de borrar."
        )

    before = (
        db.session.execute(db.text(
            "SELECT (SELECT COUNT(*) FROM products WHERE restaurant_id=:r) AS p, "
            "(SELECT COUNT(*) FROM orders WHERE restaurant_id=:r) AS o "
            "FROM DUAL"), {"r": RESTAURANT_ID}).one()
    )
    print(f"[wipe] ANTES: products={before.p} orders={before.o} (restaurant {RESTAURANT_ID})")
    print("  Borrando: order_events→order_items→orders→modifiers→products→order_counters")

    db.session.execute(db.text(
        "DELETE FROM orders WHERE restaurant_id=:r"), {"r": RESTAURANT_ID})
    db.session.execute(db.text(
        "DELETE FROM products WHERE restaurant_id=:r"), {"r": RESTAURANT_ID})
    db.session.execute(db.text(
        "DELETE FROM order_counters WHERE restaurant_id=:r"), {"r": RESTAURANT_ID})
    db.session.commit()

    after = (
        db.session.execute(db.text(
            "SELECT (SELECT COUNT(*) FROM products WHERE restaurant_id=:r) AS p, "
            "(SELECT COUNT(*) FROM orders WHERE restaurant_id=:r) AS o, "
            "(SELECT COUNT(*) FROM categories WHERE restaurant_id=:r) AS c, "
            "(SELECT COUNT(*) FROM tables WHERE restaurant_id=:r) AS t "
            "FROM DUAL"), {"r": RESTAURANT_ID}).one()
    )
    print(f"[wipe] DESPUÉS: products={after.p} orders={after.o} "
          f"categories={after.c} (conservadas) tables={after.t} (conservadas)")


# ─────────────────────────────────────────────────────────────
# Recreate (mismos productos + AutoPhoto)
# ─────────────────────────────────────────────────────────────
def phase_recreate():
    snap = _load_snapshot()
    prods = snap["products"]
    print(f"[recreate] Recreando {len(prods)} productos idénticos (AutoPhoto por producto)...")

    # category_id se conserva porque las categorías no se borraron
    created_ids = []
    for p in prods:
        product, err = ProductService.create_product(
            restaurant_id=RESTAURANT_ID,
            category_id=p["category_id"],
            name=p["name"],
            price=p["price"],
            description=p.get("description") or "",
            is_active=bool(p.get("is_active", 1)),
            is_vegetarian=bool(p.get("is_vegetarian", 0)),
            is_spicy=bool(p.get("is_spicy", 0)),
            is_featured=bool(p.get("is_featured", 0)),
        )
        if err:
            print(f"  !! {p['name']!r}: {err}")
            continue
        created_ids.append(product.id)

        # Pipeline de foto en el MISMO proceso (determinístico, respeta rate limit).
        AutoPhotoService._run(
            app, product.id, product.name, RESTAURANT_ID
        )

        # Pacing: solo si el producto va a Unsplash (no está en librería LATAM)
        if not latam_photo_library.lookup(product.name):
            import time
            time.sleep(2.5)

    db.session.commit()
    print(f"[recreate] Creados {len(created_ids)} productos. "
          "Esperando/confirmando asignación de fotos...")


# ─────────────────────────────────────────────────────────────
# Seed — ventas agosto 2026
# ─────────────────────────────────────────────────────────────
PAYMENT_MIX = ["cash"] * 38 + ["nequi"] * 28 + ["card"] * 13 + ["bancolombia"] * 21
HOUR_WEIGHTS = (
    [9, 10, 11] * 1 +            # mañana ligera
    [12, 12, 13, 13, 14, 14] * 4 +   # almuerzo
    [15, 16, 17] * 2 +           # tarde
    [18, 18, 19, 19, 20, 20, 21] * 5 +  # cena
    [22] * 1
)


def _colombia_naive_to_utc_naive(y, m, d, hour, minute):
    """Convierte hora local de Colombia a datetime naive en UTC."""
    local = datetime(y, m, d, hour, minute, tzinfo=COLOMBIA_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _pick_products(products, rng):
    """1-4 líneas; platos principales más probables."""
    n_lines = rng.choices([1, 1, 2, 2, 3, 4], weights=[25, 20, 25, 15, 10, 5])[0]
    chosen = rng.sample(products, k=min(n_lines, len(products)))
    return chosen


def phase_seed():
    snap = _load_snapshot()
    # Productos ACTIVOS recién creados (los mismos nombres/precios)
    products = Product.query.filter_by(
        restaurant_id=RESTAURANT_ID, is_active=True
    ).all()
    if not products:
        sys.exit("[error] No hay productos activos. Corre 'recreate' primero.")

    tables = [t.id for t in Table.query.filter_by(
        restaurant_id=RESTAURANT_ID, is_active=True).all()]

    rng = random.Random(20260801)
    year, month = 2026, 8
    days_in_month = 31

    orders_created = 0
    items_created = 0
    total_cop = 0
    cancelled = 0

    for day in range(1, days_in_month + 1):
        n_orders = rng.randint(20, 30)
        # horas del día ordenadas para numbering secuencial
        hours = sorted(rng.choice(HOUR_WEIGHTS) for _ in range(n_orders))

        for idx, hour in enumerate(hours, start=1):
            minute = rng.randint(0, 59)
            is_delivery = rng.random() < 0.25          # 25% domicilio (sin mesa)
            is_cancelled = rng.random() < 0.05         # 5% cancelado (realismo)
            created = _colombia_naive_to_utc_naive(year, month, day, hour, minute)
            paid = created + timedelta(minutes=rng.randint(8, 90))

            # Orden
            method = rng.choice(PAYMENT_MIX) if not is_cancelled else None
            customer = None
            phone = None
            table_id = None
            if is_delivery:
                customer = rng.choice([
                    "Carlos M.", "Laura G.", "Andrés P.", "María F.", "Jorge R.",
                    "Sofía T.", "Diego H.", "Valentina C.", "Sebastián L.", "Camila B.",
                ])
                phone = rng.choice(["3001234567", "3109876543", "3155551122",
                                    "3208887766", "3012223344"])
            elif tables:
                table_id = rng.choice(tables)

            order = Order(
                restaurant_id=RESTAURANT_ID,
                order_number=f"ORD-{idx:03d}",
                customer_name=customer,
                customer_phone=phone,
                status="cancelled" if is_cancelled else "delivered",
                total=0,
                table_id=table_id,
                payment_method=method,
                created_at=created,
                updated_at=paid,
                paid_at=paid if not is_cancelled else None,
            )
            db.session.add(order)
            db.session.flush()

            # Items
            line_products = _pick_products(products, rng)
            order_total = 0
            for prod in line_products:
                qty = rng.choices([1, 1, 2, 2, 3], weights=[40, 30, 20, 7, 3])[0]
                subtotal = prod.price * qty
                order_total += subtotal
                db.session.add(OrderItem(
                    order_id=order.id,
                    restaurant_id=RESTAURANT_ID,
                    product_name=prod.name,
                    product_price=prod.price,
                    quantity=qty,
                    subtotal=subtotal,
                ))
                items_created += 1

            order.total = order_total

            if not is_cancelled and method == "cash":
                received = (order_total // 1000 + 1) * 1000
                if received < order_total:
                    received += 1000
                order.amount_received = received
                order.change_due = received - order_total

            total_cop += 0 if is_cancelled else order_total
            cancelled += 1 if is_cancelled else 0
            orders_created += 1

            if orders_created % 100 == 0:
                db.session.commit()

        # counter del día (para consistencia con generate_order_number)
        db.session.add(OrderCounter(
            restaurant_id=RESTAURANT_ID,
            date=datetime(year, month, day).date(),
            counter=n_orders,
        ))

    db.session.commit()

    print(f"[seed] Agosto 2026 (día 1..31):")
    print(f"  órdenes totales      : {orders_created}  (canceladas: {cancelled})")
    print(f"  líneas de items      : {items_created}")
    print(f"  ventas (no cancel.)  : ${total_cop:,} COP".replace(",", "."))


# ─────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────
def phase_report():
    print(f"[report] Restaurant {RESTAURANT_ID}")

    # --- Productos / fotos ---
    prods = db.session.execute(db.text(
        "SELECT id, name, image_source, image_url FROM products "
        "WHERE restaurant_id=:r ORDER BY category_id, name"), {"r": RESTAURANT_ID}).fetchall()
    with_img = [p for p in prods if p.image_url]
    without = [p for p in prods if not p.image_url]
    print(f"\nProductos: {len(prods)} total | con foto: {len(with_img)} | sin foto: {len(without)}")

    from collections import Counter
    url_counts = Counter(p.image_url for p in with_img)
    dups = {u: c for u, c in url_counts.items() if c > 1}
    print(f"Fotos distintas: {len(url_counts)} | URLs repetidas entre productos: {len(dups)}")
    for url, cnt in sorted(dups.items(), key=lambda kv: -kv[1]):
        names = [p.name for p in with_img if p.image_url == url]
        src = next(p.image_source for p in with_img if p.image_url == url)
        print(f"  x{cnt} [{src}] {names[:6]}")
    if without:
        print("Sin foto (fallback silencioso):", [p.name for p in without][:12])

    # --- Ventas agosto ---
    aug = db.session.execute(db.text(
        "SELECT DATE(created_at) AS d, COUNT(*) AS n, COALESCE(SUM(total),0) AS total "
        "FROM orders WHERE restaurant_id=:r AND status != 'cancelled' "
        "AND created_at >= '2026-08-01 00:00:00' AND created_at < '2026-09-01 00:00:00' "
        "GROUP BY DATE(created_at) ORDER BY 1"), {"r": RESTAURANT_ID}).fetchall()
    print(f"\nVentas agosto 2026 (no canceladas, por día creado): {len(aug)} días con datos")
    if aug:
        days = [a.d.strftime('%d/%m') for a in aug]
        nums = [a.n for a in aug]
        total = sum(a.total for a in aug)
        print(f"  órdenes: min {min(nums)} / máx {max(nums)} / total {sum(nums)}")
        print(f"  facturación agosto: ${total:,} COP".replace(",", "."))

        # método de pago
        pay = db.session.execute(db.text(
            "SELECT payment_method, COUNT(*), COALESCE(SUM(total),0) "
            "FROM orders WHERE restaurant_id=:r AND status != 'cancelled' "
            "AND payment_method IS NOT NULL "
            "AND created_at >= '2026-08-01' AND created_at < '2026-09-01' "
            "GROUP BY payment_method"), {"r": RESTAURANT_ID}).fetchall()
        print("  por método:", {p.payment_method: (p[1], p[2]) for p in pay})


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
PHASES = {
    "backup": phase_backup,
    "wipe": phase_wipe,
    "recreate": phase_recreate,
    "seed": phase_seed,
    "report": phase_report,
}

app = create_app()


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in PHASES:
        print(__doc__)
        sys.exit("Fase inválida. Usa: " + " | ".join(PHASES))
    phase = sys.argv[1]
    with app.app_context():
        PHASES[phase]()


if __name__ == "__main__":
    main()
