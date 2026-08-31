"""
seed_demo_data.py — Genera datos ficticios para probar Copilot VZ.

Crea categorías, productos, extras (modifiers) y ~120 pedidos repartidos en
los últimos 60 días con patrones realistas:
  • Picos de venta a la hora del almuerzo (12-14) y cena (19-21).
  • Fines de semana más fuertes que los lunes.
  • Productos "top" que venden más.
  • Algunos pedidos cancelados (se excluyen de las métricas).
  • Teléfonos de cliente repetidos (clientes recurrentes) para "clientes nuevos".

Uso:
  python seed_demo_data.py                 # restaurante más reciente
  python seed_demo_data.py --email tu@correo.com
  python seed_demo_data.py --slug mi-restaurante
  python seed_demo_data.py --reset         # borra datos previos del restaurante antes de sembrar
"""

import os
import sys
import json
import random
import argparse
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = 'mysql+pymysql://root:root@localhost/orderfox'

from app import create_app, db
from app.models import (
    Restaurant, User, Category, Product, Modifier, Order, OrderItem,
)

# ── Catálogo de ejemplo (nombre, precio COP, peso de selección) ──
CATALOG = [
    ("Entradas", [
        ("Arepa de queso", 8000, 2),
        ("Ceviche de la casa", 18000, 1),
        ("Patacones", 9000, 2),
    ]),
    ("Platos fuertes", [
        ("Bandeja paisa", 32000, 6),
        ("Hamburguesa VZ", 20000, 5),
        ("Pollo a la plancha", 24000, 4),
        ("Pescado frito", 28000, 3),
    ]),
    ("Bebidas", [
        ("Jugo natural", 6000, 3),
        ("Gaseosa", 5000, 4),
        ("Cerveza artesanal", 9000, 3),
    ]),
    ("Postres", [
        ("Tiramisú", 12000, 2),
        ("Tres leches", 11000, 2),
    ]),
]

# Extras por producto: (nombre extra, precio extra COP)
MODIFIERS = {
    "Hamburguesa VZ": [("Queso extra", 3000), ("Tocineta", 4000), ("Huevo", 2500)],
    "Pollo a la plancha": [("Papas adicionales", 5000), ("Ensalada", 4000)],
    "Bandeja paisa": [("Huevo adicional", 3000)],
    "Cerveza artesanal": [("Vasito", 0)],
    "Jugo natural": [("Sin azúcar", 0)],
}

# Peso de pedidos por día de la semana (0=lunes .. 6=domingo).
WEEKDAY_WEIGHT = {0: 0, 1: 1, 2: 1, 3: 1, 4: 2, 5: 3, 6: 1}
# Horas con su peso (picos almuerzo y cena).
HOURS = [11, 12, 13, 14, 15, 18, 19, 20, 21, 22]
HOUR_WEIGHTS = [1, 3, 4, 3, 1, 1, 4, 4, 3, 1]

PHONES = [f"+5731{random.randint(1000000, 9999999)}" for _ in range(25)]


def pick_restaurant(email, slug):
    if email:
        u = User.query.filter_by(email=email).first()
        if u and u.restaurant:
            return u.restaurant
        print(f"⚠️  No se encontró usuario con email '{email}'.")
    if slug:
        r = Restaurant.query.filter_by(slug=slug).first()
        if r:
            return r
        print(f"⚠️  No se encontró restaurante con slug '{slug}'.")
    return Restaurant.query.order_by(Restaurant.created_at.desc()).first()


def reset_restaurant(restaurant):
    print("🧹 Borrando datos previos del restaurante...")
    OrderItem.query.filter_by(restaurant_id=restaurant.id).delete()
    Order.query.filter_by(restaurant_id=restaurant.id).delete()
    Modifier.query.filter_by(restaurant_id=restaurant.id).delete()
    Product.query.filter_by(restaurant_id=restaurant.id).delete()
    Category.query.filter_by(restaurant_id=restaurant.id).delete()
    db.session.commit()


def seed(restaurant):
    rid = restaurant.id
    print(f"🌱 Sembrando datos para restaurante: '{restaurant.name}' (id={rid}, slug={restaurant.slug})")

    # 1) Categorías + productos + extras.
    product_objs = []
    modifier_map = {}  # product_name -> [Modifier]
    for cat_name, items in CATALOG:
        cat = Category(name=cat_name, restaurant_id=rid, sort_order=0)
        db.session.add(cat)
        db.session.flush()
        for pname, price, _w in items:
            p = Product(name=pname, price=price, restaurant_id=rid, category_id=cat.id)
            db.session.add(p)
            db.session.flush()
            product_objs.append(p)
            for mname, mprice in MODIFIERS.get(pname, []):
                m = Modifier(name=mname, extra_price=mprice, restaurant_id=rid, product_id=p.id)
                db.session.add(m)
                modifier_map.setdefault(pname, []).append(m)
    db.session.commit()
    print(f"   ✓ {len(CATALOG)} categorías, {len(product_objs)} productos, "
          f"{sum(len(v) for v in modifier_map.values())} extras.")

    # 2) Pedidos en los últimos 60 días.
    weight_by_name = {n: w for (_c, items) in CATALOG for (n, _p, w) in items}
    prod_by_name = {p.name: p for p in product_objs}
    prod_names = list(prod_by_name.keys())
    prod_weights = [weight_by_name[n] for n in prod_names]

    max_ord = db.session.query(db.func.max(Order.order_number)).filter_by(restaurant_id=rid).scalar()
    seq = 1
    if max_ord and max_ord.startswith('VZ-'):
        try:
            seq = int(max_ord[3:]) + 1
        except ValueError:
            seq = 1

    today = datetime.now(timezone.utc).date()
    total_orders = 0
    total_revenue = 0
    cancelled = 0
    oldest = today

    for d in range(60, -1, -1):
        day = today - timedelta(days=d)
        # Garantizar datos en hoy y ayer para que las consultas "Hoy"/"Ayer"
        # del Copilot VZ siempre devuelvan información en la demo.
        if d <= 1:
            n_orders = random.randint(3, 6)
        else:
            base = WEEKDAY_WEIGHT[day.weekday()]
            n_orders = max(0, int(base + random.choice([0, 0, 1, 1, 2])))
        for _ in range(n_orders):
            hour = random.choices(HOURS, weights=HOUR_WEIGHTS, k=1)[0]
            minute = random.randint(0, 59)
            created = datetime(day.year, day.month, day.day, hour, minute,
                               random.randint(0, 59), tzinfo=timezone.utc)

            # Composición del pedido: 1-3 líneas.
            n_lines = random.choices([1, 2, 3], weights=[5, 3, 2])[0]
            chosen = random.choices(prod_names, weights=prod_weights, k=n_lines)
            order = Order(
                restaurant_id=rid,
                order_number=f"VZ-{seq:04d}",
                customer_phone=random.choice(PHONES),
                status='paid',
                total=0,
                created_at=created,
            )
            db.session.add(order)
            db.session.flush()
            seq += 1
            total = 0
            for pname in chosen:
                p = prod_by_name[pname]
                qty = random.choices([1, 2, 3], weights=[7, 2, 1])[0]
                mods = modifier_map.get(pname, [])
                chosen_mods = []
                if mods and random.random() < 0.5:
                    m = random.choice(mods)
                    chosen_mods.append(m.name)
                    extra = m.extra_price
                else:
                    extra = 0
                subtotal = p.price * qty + extra
                total += subtotal
                item = OrderItem(
                    order_id=order.id,
                    restaurant_id=rid,
                    product_name=p.name,
                    product_price=p.price,
                    quantity=qty,
                    subtotal=subtotal,
                    modifiers_snapshot=json.dumps(chosen_mods, ensure_ascii=False) if chosen_mods else None,
                )
                db.session.add(item)
            order.total = total
            total_revenue += total
            total_orders += 1

            # ~10% de los pedidos quedan cancelados (se excluyen de métricas).
            if random.random() < 0.10:
                order.status = 'cancelled'
                cancelled += 1

            if day < oldest:
                oldest = day

    db.session.commit()
    print(f"   ✓ {total_orders} pedidos ({cancelled} cancelados) entre "
          f"{oldest} y {today}.")
    print(f"   ✓ Ingresos totales (pagados): ${total_revenue:,} COP.")
    print("\n✅ Listo. Abre Copilot VZ y prueba preguntas como:")
    print("   • ¿Cuál es mi producto más vendido?")
    print("   • ¿Qué día de la semana vendo menos?")
    print("   • Hazme una gráfica de mis ventas")
    print("   • Compárame este mes con el anterior")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--email')
    ap.add_argument('--slug')
    ap.add_argument('--reset', action='store_true', help='Borra datos previos antes de sembrar')
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        r = pick_restaurant(args.email, args.slug)
        if not r:
            print("❌ No se encontró ningún restaurante para sembrar.")
            sys.exit(1)
        if args.reset:
            reset_restaurant(r)
        seed(r)


if __name__ == '__main__':
    main()
