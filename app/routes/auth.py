from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify, current_app
from app import db
from app.forms import LoginForm
from app.forms.auth import RegisterSetupForm
from app.models import Restaurant, TrialHistory
from app.utils.subscription import initialize_or_reset_token_wallet
from app.utils.mp_webhook import extract_mp_signature, verify_mp_signature
from app.services.auth_service import AuthService
from app.services.subscription_service import SubscriptionService
from app.utils.restaurant import get_current_restaurant
import mercadopago

auth_bp = Blueprint('auth', __name__)

from app.csrf import csrf

@auth_bp.route('/api/sync-clerk', methods=['POST'])
@csrf.exempt
def sync_clerk():
    """
    Sincroniza el usuario de Clerk con la base de datos local.
    Realiza una verificación segura consultando la API de Clerk.
    """
    try:
        data = request.get_json()
        clerk_id = data.get('clerk_id')
        email = data.get('email')
        session_id = data.get('session_id')
        current_app.logger.info(f"sync_clerk: iniciar sync email={email} clerk_id={clerk_id[:12] if clerk_id else 'None'}...")

        # 1. Verificación en el backend contra Clerk (delegada al servicio)
        verified_email, error = AuthService.verify_clerk_session(session_id, clerk_id, email)
        if error:
            return jsonify({
                'success': False,
                'message': error.get('message', 'Verification failed'),
                'error_code': error.get('error_code', 'VERIFICATION_FAILED')
            }), 401 if error.get('error_code') in ('INVALID_SESSION', 'INVALID_USER', 'EMAIL_MISMATCH', 'SESSION_USER_MISMATCH') else 500

        email = verified_email

        username = data.get('username') or email.split('@')[0]

        # El plan elegido en /planes queda en session['selected_plan'] pero el
        # servicio solo lo respeta si existe un PreRegistration. Sin esto, un
        # correo que ya usó el trial y viene a COMPRAR un plan de pago era
        # tratado como 'trial' por defecto → TRIAL_ALREADY_USED → loop
        # planes→register→login→planes. Persistirlo aquí rompe ese ciclo.
        selected_plan = session.get('selected_plan')
        if selected_plan and selected_plan != 'trial':
            try:
                AuthService.save_plan_selection(email, selected_plan)
            except Exception:
                current_app.logger.warning(
                    f"sync_clerk: no se pudo persistir plan {selected_plan} para {email}",
                    exc_info=True,
                )

        # 2. Delegar sync / creación de usuario al servicio
        user, is_new, plan_or_error = AuthService.sync_or_create_user(
            clerk_id, email, username
        )

        if user is None:
            # Bug 3: el correo ya usó el trial gratuito → redirigir a planes
            # con mensaje claro en vez de regalar otro trial.
            if plan_or_error.get('error_code') == 'TRIAL_ALREADY_USED':
                # El usuario tiene sesión Clerk válida pero NO cuenta local
                # (trial bloqueado). Guardar su identidad para que /planes
                # muestre logout y deshabilite el botón del plan trial, en vez
                # de tratarlo como visitante anónimo.
                session['clerk_id'] = clerk_id
                session['trial_blocked'] = True
                flash(plan_or_error.get('message'), 'warning')
                return jsonify({
                    'success': True,
                    'redirect_url': url_for('auth.plans'),
                    'message': plan_or_error.get('message'),
                    'trial_blocked': True,
                })

            return jsonify({
                'success': False,
                'message': plan_or_error.get('message', 'Error de registro'),
                'error_code': plan_or_error.get('error_code', 'REGISTRATION_ERROR')
            }), 500

        # v2.1.2: última acción de login gana. Si en este navegador había una
        # sesión de empleado (employee_id), el dueño la toma al autenticarse.
        session.pop('employee_id', None)
        session.pop('employee_login', None)
        session.pop('employee_slug', None)
        session['user_id'] = user.id
        session['username'] = user.username
        session['clerk_id'] = clerk_id

        if is_new:
            session['selected_plan'] = plan_or_error  # plan string
            # Bug 3c: "primera vez" = usuario recién creado Y sin historial de
            # trial previo. Sin esto, el frontend mostraba "trial activado" a
            # cualquiera con is_new_user=True aunque ya hubiera tenido cuenta.
            is_first_time = not TrialHistory.query.filter_by(email=email).first()
            return jsonify({
                'success': True,
                'message': f'¡Bienvenido! Completa tu registro para activar tu plan {plan_or_error}.',
                'is_new_user': True,
                'is_first_time': is_first_time,
                'trial_plan': plan_or_error == 'trial',
                'redirect_url': url_for('auth.setup_account')
            })

        redirect_url = url_for('dashboard.index')
        if not user.restaurant:
            # Usuario existente sin restaurante.
            if session.get('selected_plan'):
                redirect_url = url_for('auth.setup_account')
            else:
                already_used_trial = TrialHistory.query.filter_by(email=email).first() is not None
                if already_used_trial:
                    session['clerk_id'] = clerk_id
                    session['trial_blocked'] = True
                    flash(
                        'Ya usaste tu período de prueba gratuito. Elige un plan para continuar.',
                        'warning'
                    )
                    redirect_url = url_for('auth.plans')
                else:
                    session['selected_plan'] = 'trial'
                    redirect_url = url_for('auth.setup_account')

        return jsonify({
            'success': True,
            'redirect_url': redirect_url
        })

    except Exception as e:
        current_app.logger.error(f"sync_clerk: ERROR FATAL: {type(e).__name__}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Error interno del servidor: {type(e).__name__}',
            'error_code': 'INTERNAL_ERROR'
        }), 500


@auth_bp.route('/api/seed-full', methods=['POST'])
@csrf.exempt
def seed_full():
    """Borra todo y recrea menú completo + ventas agosto 2026."""
    import random
    from datetime import datetime, timedelta, timezone
    from app.models import db, Restaurant, Category, Product, Order, OrderItem, User

    API_KEY = 'velzia-seed-2026'
    if request.headers.get('X-Seed-Key') != API_KEY:
        return jsonify({'error': 'unauthorized'}), 401

    user = User.query.filter_by(email='velziaoficial@gmail.com').first()
    if not user or not user.restaurant:
        return jsonify({'error': 'user or restaurant not found'}), 404

    restaurant = user.restaurant
    rid = restaurant.id

    OrderItem.query.filter_by(restaurant_id=rid).delete()
    Order.query.filter_by(restaurant_id=rid).delete()
    Product.query.filter_by(restaurant_id=rid).delete()
    Category.query.filter_by(restaurant_id=rid).delete()
    db.session.flush()

    cats_data = [
        ('Entradas y Para Picar', 'Aperitivos y bocaditos para compartir', 1),
        ('Sopas Calientes', 'Sopas tradicionales colombianas', 2),
        ('Platos Fuertes', 'Platos principales del día', 3),
        ('Acompañamientos', 'Guarniciones y extras', 4),
        ('Bebidas Frías', 'Refrescos, jugos y cervezas', 5),
        ('Bebidas Calientes', 'Café, tinto y chocolate', 6),
        ('Postres', 'Dulces tradicionales colombianos', 7),
    ]
    cats = {}
    for name, desc, order in cats_data:
        cat = Category(restaurant_id=rid, name=name, description=desc, sort_order=order)
        db.session.add(cat)
        db.session.flush()
        cats[name] = cat

    U = 'https://images.unsplash.com/photo-{}?q=80&w=800&auto=format&fit=crop'
    products = [
        # Entradas y Para Picar (8)
        ('Empanadas Colombianas x3', 'Empanadas de carne con hogao, servidas con ají', 8500, 'Entradas y Para Picar', True, False, True, U.format('1601000938-db3abbd3e1d7')),
        ('Patacones con Hogao', 'Plátano verde frito doble cocción con hogao de tomate y cebolla', 9500, 'Entradas y Para Picar', True, False, False, U.format('1562967916-eb82221dfb92')),
        ('Chicharrón con Arepa', 'Chicharrón crujiente con arepa antioqueña y limón', 12000, 'Entradas y Para Picar', False, False, False, U.format('1558030006-f6bff2fc5d50')),
        ('Marranitas', 'Bolitas de plátano verde rellenas de chicharrón, estilo Chocó', 10000, 'Entradas y Para Picar', False, False, False, U.format('1551754655-59e33e7c10e9')),
        ('Aborrajados', 'Tajadas de plátano maduro rellenas de queso, rebozadas y fritas', 9000, 'Entradas y Para Picar', True, False, False, U.format('1565299585323-38d6b0865b47')),
        ('Arepa con Queso', 'Arepa de maíz con queso derretido y mantequilla', 6000, 'Entradas y Para Picar', True, False, False, U.format('1599974579688-8dbdd335c77f')),
        ('Buñuelos Colombianos', 'Buñuelos de maíz y queso, crujientes por fuera y esponjosos por dentro', 5000, 'Entradas y Para Picar', True, False, False, U.format('1495474472287-4d71bcdd2085')),
        ('Empanadas de Pollo x3', 'Empanadas de pollo desmechado con especias', 8500, 'Entradas y Para Picar', True, False, False, U.format('1604908176997-125f25cc6f3d')),

        # Sopas Calientes (5)
        ('Sancocho de Gallina', 'Sancocho tradicional con gallina criolla, yuca, plátano, mazorca y cilantro', 18000, 'Sopas Calientes', False, False, True, U.format('1547592180-85f173990554')),
        ('Ajiaco Santafereño', 'Ajiaco bogotano con tres tipos de papa, guascas, mazorca y pollo', 17000, 'Sopas Calientes', False, False, False, U.format('1672300389082-540b049e4786')),
        ('Sancocho de Pescado', 'Sancocho de pescado fresco con leche de coco y plátano', 19000, 'Sopas Calientes', False, False, False, U.format('1603133872878-684f208fb84b')),
        ('Caldo de Costilla', 'Caldo reconfortante de costilla de res con papa y cilantro', 12000, 'Sopas Calientes', False, False, False, U.format('1547592166-23ac45744acd')),
        ('Sopa de Arroz con Pollo', 'Sopa espesa de arroz con pollo desmechado y verduras', 13000, 'Sopas Calientes', False, False, False, U.format('1562802378-074508538b76')),

        # Platos Fuertes (11)
        ('Bandeja Paisa', 'Frijoles, arroz, carne molida, chicharrón, huevo frito, plátano maduro, arepa y aguacate', 28000, 'Platos Fuertes', False, False, True, U.format('1565557244-65388e869022')),
        ('Arroz con Pollo', 'Arroz amarillo con pollo, verduras y cerveza, servido con patacón', 22000, 'Platos Fuertes', False, False, False, U.format('1598515214211-89d3c73ae83b')),
        ('Sudado de Res', 'Carne de res guisada en salsa de tomate con papa, plátano verde y arroz', 23000, 'Platos Fuertes', False, False, False, U.format('1544025162-d76694265947')),
        ('Pollo Sudado', 'Pollo en salsa criolla con arroz, papa y plátano', 20000, 'Platos Fuertes', False, False, False, U.format('1598103442097-870d22c6e8f6')),
        ('Lomo al Trapo', 'Lomo de res envuelto en sal cocido al carbón, con papa criolla y ají', 32000, 'Platos Fuertes', False, False, False, U.format('1558030137-a56c1b004fa3')),
        ('Punta de Anca en Salsa', 'Punta de anca en salsa de champiñones con arroz y ensalada', 29000, 'Platos Fuertes', False, False, False, U.format('1558030006-f6bff2fc5d50')),
        ('Mojarra Frita', 'Mojarra entera frita crispy con patacones, arroz con coco y ensalada', 25000, 'Platos Fuertes', False, False, False, U.format('1559847844-5315695dadae')),
        ('Chuleta Valluna', 'Chuleta de cerdo empanizada al estilo valluna con arroz, ensalada y patacón', 24000, 'Platos Fuertes', False, False, False, U.format('1432139555190-58524dae6a55')),
        ('Bandeja de Montañera', 'Carne asada, pollo a la plancha, arroz, frijoles, tajadas y ensalada', 30000, 'Platos Fuertes', False, False, False, U.format('1574484284002-952d92456975')),
        ('Seco de Chivo', 'Chivo guisado estilo Caribe con arroz con coco y plátano maduro', 26000, 'Platos Fuertes', False, False, False, U.format('1504674900247-0877df9cc836')),
        ('Trucha con Patacón', 'Trucha en salsa de limón con patacón y arroz', 27000, 'Platos Fuertes', False, False, False, U.format('1519708227418-c8fd9a32b7a2')),

        # Acompañamientos (7)
        ('Patacón Solo', 'Patacón crujiente doble cocción', 4000, 'Acompañamientos', True, False, False, U.format('1562967916-eb82221dfb92')),
        ('Tajada de Plátano Maduro', 'Tajada frita de plátano maduro', 3500, 'Acompañamientos', True, False, False, U.format('1571771894821-ce9b6c11b08e')),
        ('Arroz Blanco', 'Porción de arroz blanco suelto', 3000, 'Acompañamientos', True, False, False, U.format('1551754655-59e33e7c10e9')),
        ('Frijoles Colorados', 'Frijoles guisados estilo paisa', 4500, 'Acompañamientos', True, False, False, U.format('1543339608-b70e5d1cee63')),
        ('Ensalada Mixta', 'Lechuga, tomate, zanahoria y aguacate', 5000, 'Acompañamientos', True, False, False, U.format('1512621776951-a57141f2eefd')),
        ('Aguacate', 'Media unidad de aguacate fresco', 4000, 'Acompañamientos', True, False, False, U.format('1523049673857-eb18f1d7b578')),
        ('Yuca con Mojo', 'Yuca hervida con salsa de ajo y limón', 5500, 'Acompañamientos', True, False, False, U.format('1600335895229-6e75511892c8')),

        # Bebidas Frías (13)
        ('Limonada Natural', 'Limonada fresca con hielo y hierbabuena', 5000, 'Bebidas Frías', True, False, False, U.format('1621263764928-df1444c58b4c')),
        ('Limonada de Coco', 'Limonada cremosa de coco, refrescante y tropical', 7000, 'Bebidas Frías', True, False, False, U.format('1513558161293-cdaf765ed2fd')),
        ('Jugo de Mango', 'Jugo natural de mango colombiano', 5500, 'Bebidas Frías', True, False, False, U.format('1623065422902-30a2d299bbe4')),
        ('Jugo de Guanábana', 'Jugo natural de guanábana', 5500, 'Bebidas Frías', True, False, False, U.format('1600271886742-f049cd451bba')),
        ('Jugo de Maracuyá', 'Jugo natural de maracuyá', 5500, 'Bebidas Frías', True, False, False, U.format('1621506289937-a8e4df240d0b')),
        ('Jugo de Corozo', 'Jugo natural de corozo, fruto del Chocó', 6000, 'Bebidas Frías', True, False, False, U.format('1595981267035-7b04ca84a82d')),
        ('Gaseosa Personal', 'Coca-Cola, Sprite o Fanta (330ml)', 3500, 'Bebidas Frías', True, False, False, U.format('1523677011781-c91d1bbe2f9e')),
        ('Agua Botella', 'Agua pura sin gas (600ml)', 3000, 'Bebidas Frías', True, False, False, U.format('1560022154-392c4af77048')),
        ('Cerveza Águila', 'Cerveza rubia colombiana bien fría', 4500, 'Bebidas Frías', False, False, False, U.format('1618183479302-1e0aa382c36b')),
        ('Cerveza Póker', 'Cerveza pilsner colombiana', 4500, 'Bebidas Frías', False, False, False, U.format('1566633806327-68e152aaf26d')),
        ('Cerveza Club Colombia', 'Cerveza premium colombiana dorada', 7000, 'Bebidas Frías', False, False, False, U.format('1535958636474-b021ee887b13')),
        ('Coronita', 'Cerveza importada mexicana', 6500, 'Bebidas Frías', False, False, False, U.format('1571613316887-6f8d5cbf7ef7')),
        ('Michelada', 'Cerveza con limón, salsa picante y sal', 8000, 'Bebidas Frías', False, True, False, U.format('1589132971214-ed8169976abd')),

        # Bebidas Calientes (5)
        ('Tinto Colombiano', 'Café tinto tradicional, servido caliente', 2500, 'Bebidas Calientes', True, False, False, U.format('1514432324607-a7df424d9ca7')),
        ('Tinto con Leche', 'Café tinto con leche caliente', 3500, 'Bebidas Calientes', True, False, False, U.format('1572442388796-11668a67e53d')),
        ('Cappuccino', 'Espresso con espuma de leche y cacao', 6000, 'Bebidas Calientes', True, False, False, U.format('1572442388796-11668a67e53d')),
        ('Chocolate Santafereño', 'Chocolate caliente espeso con queso y arepa', 7000, 'Bebidas Calientes', True, False, False, U.format('1647919234555-3d06e2c923f4')),
        ('Aromática', 'Té de hierbabuena, manzanilla o tilo', 3500, 'Bebidas Calientes', True, False, False, U.format('1556679343-c7306c1976bc')),

        # Postres (9)
        ('Arroz con Leche', 'Arroz con leche tradicional colombiano con canela y coco rallado', 7000, 'Postres', True, False, False, U.format('1532556660262-1c45d5fae825')),
        ('Torta de Choclo', 'Torta de choclo dulce horneada, estilo tradicional', 8000, 'Postres', True, False, False, U.format('1578985545062-69928b1d9587')),
        ('Postre de Natas', 'Dulce cremoso de natas con arepa o galleta', 7000, 'Postres', True, False, False, U.format('1488477181946-6428a0291777')),
        ('Manjar Blanco', 'Dulce tradicional de leche y azúcar, servido frío', 7500, 'Postres', True, False, False, U.format('1571115177098-24ec42ed204d')),
        ('Gelatina de Pata', 'Gelatina tradicional de colación con coco rallado', 6000, 'Postres', True, False, False, U.format('1488477181946-6428a0291777')),
        ('Cholado', 'Copa de frutas frescas con hielo raspado, leche condensada y salsas', 10000, 'Postres', True, False, False, U.format('1557006001-1d7c8b6d0cc3')),
        ('Helado Artesanal x2 Bolas', 'Dos bolas de helado artesanal (vainilla, chocolate, fresa o mora)', 6500, 'Postres', True, False, False, U.format('1497034825429-c343d7c6a68f')),
        ('Oblea con Arequipe', 'Oblea rellena con arequipe y queso cremoso', 5500, 'Postres', True, False, False, U.format('1624300626297-1d2b4e41d6a7')),
        ('Hamburguesa Especial', 'Hamburguesa con doble carne, queso cheddar, lechuga y tomate', 15000, 'Platos Fuertes', False, False, True, U.format('1568901346375-23c9450c58cd')),
    ]

    count = 0
    for name, desc, price, cat_name, veg, spicy, featured, img_url in products:
        p = Product(
            restaurant_id=rid,
            category_id=cats[cat_name].id,
            name=name,
            description=desc,
            price=price,
            image_url=img_url,
            is_active=True,
            is_vegetarian=veg,
            is_spicy=spicy,
            is_featured=featured,
        )
        db.session.add(p)
        count += 1

    restaurant.cuisine_type = 'colombiano'
    restaurant.estimated_time = 25
    restaurant.brand_color = '#FF6B00'
    db.session.flush()

    # ── Ventas agosto 2026 ──
    all_products = Product.query.filter_by(restaurant_id=rid, is_active=True).all()
    pw = []
    for p in all_products:
        w = 10
        if p.is_featured: w = 25
        if p.price and p.price < 6000: w = 15
        if p.price and p.price > 25000: w = 5
        pw.append((p, w))

    names = [
        'Carlos M.', 'María L.', 'Andrés P.', 'Laura G.', 'Diego R.',
        'Sofía H.', 'Juan D.', 'Valentina T.', 'Sebastián M.', 'Camila V.',
        'Mateo S.', 'Isabella C.', 'Santiago A.', 'Luciana F.', 'Tomás B.',
        'Gabriela E.', 'Nicolás K.', 'Daniela O.', 'Alejandro N.', 'Paula J.',
        None, None, None, None, None,
    ]
    phones = [
        '+57 300 123 4567', '+57 310 234 5678', '+57 315 345 6789',
        '+57 320 456 7890', '+57 301 567 8901', None, None, None, None, None,
    ]
    pms = ['cash', 'nequi', 'bancolombia', 'card']
    pmw = [35, 30, 20, 15]
    COT = timezone(timedelta(hours=-5))
    order_num = 1

    for day in range(1, 32):
        dt = datetime(2026, 8, day, tzinfo=COT)
        n = random.randint(10, 14) if dt.weekday() >= 5 else random.randint(6, 10)
        for _ in range(n):
            h = random.choices([11,12,13,14,18,19,20,21,22], weights=[8,20,18,10,12,18,15,10,5])[0]
            created = datetime(2026, 8, day, h, random.randint(0,59), random.randint(0,59), tzinfo=COT)
            created_utc = created.astimezone(timezone.utc)
            pm = random.choices(pms, weights=pmw)[0]
            status = random.choices(['delivered','delivered','delivered','cancelled'], weights=[88,4,4,4])[0]
            n_items = random.choices([1,2,3,4], weights=[20,40,30,10])[0]
            chosen = random.choices(pw, weights=[w for _,w in pw], k=n_items)
            total = 0
            items_list = []
            for prod, _ in chosen:
                qty = random.choices([1,2,3], weights=[60,30,10])[0]
                sub = prod.price * qty
                total += sub
                items_list.append({'name': prod.name, 'price': prod.price, 'qty': qty, 'subtotal': sub})
            ar = None; cd = None
            if pm == 'cash':
                bills = [5000,10000,15000,20000,30000,50000]
                ar = next((b for b in bills if b >= total), total+5000)
                cd = ar - total
            order = Order(
                restaurant_id=rid, order_number=f'ORD-{order_num:03d}',
                customer_name=random.choice(names), customer_phone=random.choice(phones),
                status=status, total=total, payment_method=pm,
                amount_received=ar, change_due=cd,
                paid_at=created_utc if status=='delivered' else None,
                created_at=created_utc, updated_at=created_utc+timedelta(minutes=random.randint(15,45)),
            )
            db.session.add(order)
            db.session.flush()
            for it in items_list:
                db.session.add(OrderItem(
                    order_id=order.id, restaurant_id=rid,
                    product_name=it['name'], product_price=it['price'],
                    quantity=it['qty'], subtotal=it['subtotal'],
                ))
            order_num += 1

    db.session.commit()
    return jsonify({'success': True, 'products': count, 'orders': order_num - 1})


@auth_bp.route('/api/sync-clerk-redirect')
def sync_clerk_redirect():
    return render_template('auth/sync_clerk.html')


@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        user = AuthService.get_user(session['user_id'])
        # v2.1.1: cookie de sesión VIEJA (pre-fix) donde el login del empleado
        # guardaba user_id. Un empleado (tiene PIN) nunca debe ser tratado como
        # dueño: limpiar la sesión y mostrar el login del admin, para no quedar
        # atrapado en el loop raíz → dashboard → portal del empleado.
        if user is not None and user.pin_hash is not None:
            session.pop('user_id', None)
            session.pop('username', None)
            session.pop('clerk_id', None)
            form = LoginForm()
            return render_template('auth/index.html', form=form)
        # Cuenta logueada sin restaurante: NO ir a dashboard.index (require_active
        # lanza "Tu cuenta no está asociada a ningún restaurante" y redirige en
        # loop). Llevar al flujo correcto según su estado.
        if user and not user.restaurant:
            if session.get('selected_plan'):
                return redirect(url_for('auth.setup_account'))
            used_trial = TrialHistory.query.filter_by(email=user.email).first() is not None
            if used_trial:
                session['trial_blocked'] = True
                return redirect(url_for('auth.plans'))
            return redirect(url_for('auth.setup_account'))
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user, error = AuthService.authenticate(
            form.email.data, form.password.data
        )
        if user:
            # v2.1.2: última acción de login gana. Si en este navegador había
            # una sesión de empleado, el dueño la toma al iniciar sesión.
            session.pop('employee_id', None)
            session.pop('employee_login', None)
            session['user_id'] = user.id
            session['username'] = user.username

            if user.restaurant and not user.restaurant.is_active:
                session['pending_restaurant_id'] = user.restaurant.id
                flash('Tu suscripción está pendiente de pago.', 'info')
                return redirect(url_for('auth.payment'))

            return redirect(url_for('dashboard.index'))
        else:
            flash('Email o contraseña incorrectos')
    return render_template('auth/index.html', form=form)


@auth_bp.route('/privacy')
def privacy():
    return redirect(url_for('auth.legal'))


@auth_bp.route('/terms')
def terms():
    return redirect(url_for('auth.legal'))


@auth_bp.route('/legal')
def legal():
    return render_template('dashboard/legal.html')


@auth_bp.route('/planes')
def plans():
    has_restaurant = False
    if 'user_id' in session:
        user = AuthService.get_user(session['user_id'])
        if user:
            has_restaurant = user.restaurant is not None
            # Usuario con cuenta local pero sin restaurante. Si ya usó el trial,
            # DEBE poder ver /planes para elegir un plan pago; solo se le fuerza
            # a setup-account si todavía no usó el trial (flujo de registro).
            if not user.restaurant:
                used_trial = TrialHistory.query.filter_by(email=user.email).first() is not None
                if not used_trial:
                    return redirect(url_for('auth.setup_account'))
    return render_template('auth/plans.html', has_restaurant=has_restaurant)


@auth_bp.route('/register', methods=['GET'])
def register():
    plan = request.args.get('plan')
    if plan:
        session['selected_plan'] = plan

    # Usuario ya autenticado que eligió un plan desde /planes. No debe pasar
    # por register_verify (que redirige a /login → dashboard.index → 404 por
    # require_active "sin restaurante"). Va directo a setup-account con el
    # plan ya guardado en sesión.
    if 'user_id' in session:
        user = AuthService.get_user(session['user_id'])
        if user and not user.restaurant:
            return redirect(url_for('auth.setup_account'))

    selected_plan = session.get('selected_plan', 'emprendedor')
    return render_template('auth/register_verify.html', step='email', plan=selected_plan)


@auth_bp.route('/api/save-plan-selection', methods=['POST'])
def save_plan_selection():
    """
    Endpoint que guarda la pre-registración cuando el usuario selecciona un plan.
    """
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    plan = data.get('plan', '').strip()

    if not email or not plan:
        return jsonify({
            'success': False,
            'message': 'Email y plan son requeridos'
        }), 400

    result, error = AuthService.save_plan_selection(email, plan)
    if error:
        return jsonify({
            'success': False,
            'message': error['message']
        }), 400

    return jsonify({
        'success': True,
        'message': f'Plan {plan} guardado. Redirigiendo a login...'
    })


@auth_bp.route('/setup-account', methods=['GET', 'POST'])
def setup_account():
    if 'user_id' not in session:
        return redirect(url_for('auth.register'))

    form = RegisterSetupForm()

    user = AuthService.get_user(session['user_id'])
    if not user:
        return redirect(url_for('auth.register'))

    if user.restaurant:
        return redirect(url_for('dashboard.index'))

    # Defensivo: usuario sin restaurante que ya usó el trial y aún no eligió
    # plan. No debe quedar en setup-account con plan=None (el template lo
    # muestra como elite $50.000/mes). Forzar elección en /planes.
    if not session.get('selected_plan') and user.email:
        used_trial = TrialHistory.query.filter_by(email=user.email).first() is not None
        if used_trial:
            session['clerk_id'] = user.clerk_id
            session['trial_blocked'] = True
            flash(
                'Ya usaste tu período de prueba gratuito. Elige un plan para continuar.',
                'warning'
            )
            return redirect(url_for('auth.plans'))

    email = user.email

    if user.clerk_id:
        form.admin_name.validators = []
        form.password.validators = []
        form.confirm_password.validators = []

    if form.validate_on_submit():
        if not form.accept_terms.data:
            flash('Debes aceptar los Términos y Condiciones y la Política de Datos para continuar.', 'warning')
            return render_template('auth/register_setup.html', form=form,
                                   plan=session.get('selected_plan'), user=user)
        selected_plan = session.get('selected_plan', 'emprendedor')
        is_trial = selected_plan == 'trial'

        # Trial eligibility check
        if is_trial:
            blocked, msg = AuthService.check_trial_eligibility(
                email, form.phone.data
            )
            if blocked:
                # No dejar al usuario atascado en setup-account con plan trial:
                # redirigir a /planes para que elija un plan pago. register()
                # con user_id en sesión lo devolverá aquí con el plan ya elegido.
                session['trial_blocked'] = True
                flash(msg, 'warning')
                return redirect(url_for('auth.plans'))

        restaurant, error_msg = AuthService.create_restaurant_from_setup(
            user=user,
            email=email,
            restaurant_name=form.restaurant_name.data,
            phone=form.phone.data,
            selected_plan=selected_plan,
            admin_name=form.admin_name.data,
            password=form.password.data,
        )

        if error_msg:
            flash(error_msg)
            return render_template('auth/register_setup.html', form=form,
                                   plan=selected_plan, user=user)

        if is_trial:
            # Email de bienvenida justo después de crear el restaurante en DB.
            # No bloquea el flujo si el envío falla.
            AuthService.send_welcome_email(restaurant, user)
            session['username'] = user.username
            return redirect(url_for('dashboard.index'))
        else:
            session['pending_restaurant_id'] = restaurant.id
            return redirect(url_for('auth.payment'))

    return render_template('auth/register_setup.html', form=form,
                           plan=session.get('selected_plan'), user=user)


@auth_bp.route('/renew', methods=['GET'])
def renew():
    """
    Ruta de renovación para usuarios ya autenticados.
    """
    if 'user_id' not in session:
        flash('Debes iniciar sesión para renovar tu suscripción.')
        return redirect(url_for('auth.login'))

    user = AuthService.get_user(session['user_id'])
    if not user or not user.restaurant:
        flash('No se encontró información de tu cuenta.')
        return redirect(url_for('dashboard.index'))

    restaurant = user.restaurant

    plan = request.args.get('plan')
    if plan and plan in ('emprendedor', 'crecimiento', 'elite'):
        session['selected_plan'] = plan
        session['pending_plan_change'] = plan
    else:
        current_plan = restaurant.plan_type
        if current_plan == 'trial':
            flash('Selecciona un plan de pago para continuar.')
            return redirect(url_for('auth.plans'))
        session['selected_plan'] = current_plan
        session['pending_plan_change'] = None

    session['pending_restaurant_id'] = restaurant.id
    session['is_renewal'] = True

    return redirect(url_for('auth.payment'))


@auth_bp.route('/payment', methods=['GET', 'POST'])
def payment():
    restaurant_id = session.get('pending_restaurant_id')

    if not restaurant_id and 'user_id' in session:
        current_res = get_current_restaurant()
        if current_res:
            restaurant_id = current_res.id
            session['pending_restaurant_id'] = restaurant_id

    if not restaurant_id:
        return redirect(url_for('auth.register'))

    restaurant = Restaurant.query.get(restaurant_id)
    if not restaurant:
        return redirect(url_for('auth.register'))

    selected_plan_key = session.get('selected_plan', 'crecimiento')
    plan_info = SubscriptionService.get_plan_info(selected_plan_key)

    if plan_info['price_raw'] <= 0:
        flash('Plan inválido para pago. Por favor selecciona un plan de pago.')
        return redirect(url_for('auth.plans'))

    base_url = current_app.config.get('BASE_URL', request.url_root.rstrip('/'))
    preference_data, _, coupon = SubscriptionService.build_mp_preference_data(
        selected_plan_key, restaurant_id, base_url
    )

    sdk = mercadopago.SDK(current_app.config.get('MP_ACCESS_TOKEN'))
    checkout_url, preference_id, error_msg = SubscriptionService.create_mp_preference(sdk, preference_data)
    if preference_id and coupon:
        try:
            SubscriptionService.reserve_coupon(coupon, preference_id)
        except Exception:
            current_app.logger.warning('Error reservando cupón', exc_info=True)

    if error_msg:
        flash(error_msg)
        return redirect(url_for('auth.plans'))

    return redirect(checkout_url)


@auth_bp.route('/payment-callback')
def payment_callback():
    status = request.args.get('status')
    ext_ref = request.args.get('external_reference', '')

    restaurant_id = None
    plan_type = None
    if ':' in ext_ref:
        parts = ext_ref.split(':', 1)
        try:
            restaurant_id = int(parts[0])
            plan_type = parts[1]
        except (ValueError, IndexError):
            restaurant_id = None

    # La Sorpresa Velzia se entrega dentro de _finalize_payment
    # (recompensa + email), sin depender de n8n.
    restaurant, user, _ = SubscriptionService.process_payment_callback(
        status, restaurant_id, plan_type,
        payment_id=request.args.get('payment_id'),
    )

    if not restaurant:
        flash('No pudimos confirmar tu pago. Regresa e inténtalo de nuevo.')
        return redirect(url_for('auth.payment'))

    is_renewal = session.get('is_renewal', False)

    # Reset tokens on approved payment
    if status == 'approved' and user:
        mp_payment_id = request.args.get('payment_id')
        initialize_or_reset_token_wallet(user, is_reset=True, mp_payment_id=mp_payment_id)

    # Clean up session
    session.pop('otp', None)
    session.pop('register_email', None)
    session.pop('otp_verified', None)
    session.pop('pending_restaurant_id', None)
    session.pop('selected_plan', None)
    session.pop('is_renewal', None)
    session.pop('pending_plan_change', None)

    if status == 'approved':
        if is_renewal:
            return redirect(url_for('dashboard.subscription'))
        return redirect(url_for('auth.login'))
    else:
        flash('Tu pago está pendiente de aprobación. Hemos activado tu acceso temporalmente.')
        if is_renewal:
            return redirect(url_for('dashboard.subscription'))
        return redirect(url_for('auth.login'))


@auth_bp.route('/webhook', methods=['POST'])
@csrf.exempt
def webhook():
    """
    Recibe notificaciones de Mercado Pago (formato IPN legacy).
    Verifica firma HMAC cuando `MP_WEBHOOK_SECRET` está configurado.
    Para webhooks nuevos, usar `POST /api/v1/webhooks/mercadopago`.
    """
    try:
        data = request.get_json(silent=True) or {}

        payment_id = None

        if data and data.get("type") == "payment":
            payment_id = data.get("data", {}).get("id")

        if not payment_id:
            topic = request.args.get('topic') or request.args.get('type')
            if topic == 'payment':
                payment_id = request.args.get('id') or request.args.get('data.id')

        # Fail-closed (alineado con /api/v1/webhooks/mercadopago): sin secret
        # configurado NO se procesa nada; con secret, la firma es obligatoria.
        webhook_secret = current_app.config.get('MP_WEBHOOK_SECRET')
        if not webhook_secret:
            current_app.logger.error("WEBHOOK LEGACY: MP_WEBHOOK_SECRET no configurado")
            return jsonify({'success': False, 'error': 'webhook_not_configured'}), 503

        if payment_id:
            ts, v1 = extract_mp_signature(request.headers)
            if not verify_mp_signature(str(payment_id), ts, v1, webhook_secret):
                current_app.logger.warning(
                    f"WEBHOOK LEGACY: Firma inválida para payment_id={payment_id}"
                )
                return jsonify({'success': False, 'error': 'invalid_signature'}), 401

        if payment_id:
            access_token = current_app.config.get('MP_ACCESS_TOKEN')
            result = SubscriptionService.process_mp_webhook_payment(payment_id, access_token)
            if result:
                current_app.logger.info(
                    f"WEBHOOK: Activated restaurant {result['restaurant_id']}"
                )

        return jsonify({'success': True}), 200
    except Exception as e:
        current_app.logger.error(f"WEBHOOK ERROR: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'internal_error'}), 500


@auth_bp.route('/logout')
def logout():
    session.clear()
    return render_template('auth/logout_clerk.html')
