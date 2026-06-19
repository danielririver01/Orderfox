import json
from flask import Blueprint, jsonify, render_template, Response
from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from app.schemas import (
    SuccessResponse, ErrorResponse, PaginationMeta, PaginatedData,
    RestaurantSchema, UserSchema, CategorySchema, ProductSchema,
    ProductCreate, ModifierSchema, OrderSchema, OrderCreate,
    OrderItemSchema, TableSchema, AITokenWalletSchema,
    LoginRequest, SyncClerkRequest,
)

api_docs_bp = Blueprint('api_docs', __name__, url_prefix='/api/docs')

# ─── Lazy APISpec builder ──────────────────────────────────────────────

_spec = None


def _build_spec():
    """Build the APISpec instance once and cache it.

    This function is idempotent — subsequent calls return the cached spec.
    """
    global _spec
    if _spec is not None:
        return _spec

    _spec = APISpec(
        title='Orderfox API',
        version='1.3.0',
        openapi_version='3.0.3',
        info=dict(
            description='API REST para la plataforma de pedidos de restaurantes Orderfox.',
        ),
        plugins=[MarshmallowPlugin()],
    )

    # ── Security Schemes ───────────────────────────────────────────────
    _spec.components.security_scheme('api_key', {
        'type': 'apiKey',
        'in': 'header',
        'name': 'x-api-key',
        'description': 'API Key para comunicación server-to-server (bypasea rate limiting)',
    })
    _spec.components.security_scheme('bearer_jwt', {
        'type': 'http',
        'scheme': 'bearer',
        'bearerFormat': 'JWT',
        'description': 'JWT de Clerk (24h expiración). Usar para API móvil/externa.',
    })

    # ── Register Schemas ───────────────────────────────────────────────
    # Container schemas (con Nested) se registran DESPUÉS de los simples.
    # ModifierSchema y OrderItemSchema NO se registran explícitamente
    # porque el MarshmallowPlugin los auto-registra al procesar los Nested
    # fields en ProductSchema y OrderSchema respectivamente.
    _spec.components.schema('SuccessResponse', schema=SuccessResponse)
    _spec.components.schema('ErrorResponse', schema=ErrorResponse)
    _spec.components.schema('PaginationMeta', schema=PaginationMeta)
    _spec.components.schema('Restaurant', schema=RestaurantSchema)
    _spec.components.schema('User', schema=UserSchema)
    _spec.components.schema('Category', schema=CategorySchema)
    _spec.components.schema('ProductCreate', schema=ProductCreate)
    _spec.components.schema('OrderCreate', schema=OrderCreate)
    _spec.components.schema('Table', schema=TableSchema)
    _spec.components.schema('AITokenWallet', schema=AITokenWalletSchema)
    _spec.components.schema('LoginRequest', schema=LoginRequest)
    _spec.components.schema('SyncClerkRequest', schema=SyncClerkRequest)
    # Container schemas — auto-registran Modifier + OrderItem via Nested
    _spec.components.schema('Product', schema=ProductSchema)
    _spec.components.schema('Order', schema=OrderSchema)

    # ── Register Paths ─────────────────────────────────────────────────
    _register_paths(_spec)

    return _spec


# ─── Path Registrations ─────────────────────────────────────────────────

def _register_paths(spec):
    """Register all API paths with the APISpec instance."""

    # ── Auth ──────────────────────────────────────────────────────────

    spec.path(
        path='/api/auth/login',
        operations=dict(
            post=dict(
                tags=['Autenticación'],
                summary='Inicio de sesión tradicional',
                description='Autenticación con email y contraseña.',
                requestBody=dict(
                    required=True,
                    content={'application/json': {'schema': 'LoginRequest'}},
                ),
                responses={
                    '200': {'description': 'Login exitoso', 'content': {'application/json': {'schema': 'SuccessResponse'}}},
                    '401': {'description': 'Credenciales inválidas', 'content': {'application/json': {'schema': 'ErrorResponse'}}},
                },
            ),
        ),
    )

    spec.path(
        path='/api/auth/sync-clerk',
        operations=dict(
            post=dict(
                tags=['Autenticación'],
                summary='Sincronizar usuario de Clerk',
                description='Crea o recupera un usuario desde Clerk OAuth.',
                requestBody=dict(
                    required=True,
                    content={'application/json': {'schema': 'SyncClerkRequest'}},
                ),
                responses={
                    '200': {'description': 'Usuario existente', 'content': {'application/json': {'schema': 'SuccessResponse'}}},
                    '201': {'description': 'Nuevo usuario creado con trial'},
                    '409': {'description': 'Trial ya usado', 'content': {'application/json': {'schema': 'ErrorResponse'}}},
                },
            ),
        ),
    )

    # ── Products ──────────────────────────────────────────────────────

    spec.path(
        path='/api/products',
        operations=dict(
            get=dict(
                tags=['Productos'],
                summary='Listar productos',
                description='Obtiene la lista de productos del restaurante autenticado.',
                security=[{'bearer_jwt': []}],
                parameters=[
                    {'name': 'category_id', 'in': 'query', 'schema': {'type': 'integer'}, 'description': 'Filtrar por categoría'},
                    {'name': 'active_only', 'in': 'query', 'schema': {'type': 'boolean'}, 'description': 'Solo activos'},
                    {'name': 'page', 'in': 'query', 'schema': {'type': 'integer'}, 'description': 'Número de página'},
                    {'name': 'per_page', 'in': 'query', 'schema': {'type': 'integer'}, 'description': 'Items por página'},
                ],
                responses={
                    '200': {'description': 'Lista de productos', 'content': {'application/json': {'schema': 'SuccessResponse'}}},
                    '404': {'description': 'Restaurante no encontrado'},
                },
            ),
            post=dict(
                tags=['Productos'],
                summary='Crear producto',
                description='Crea un nuevo producto en el menú.',
                security=[{'bearer_jwt': []}],
                requestBody=dict(
                    required=True,
                    content={'multipart/form-data': {'schema': 'ProductCreate'}},
                ),
                responses={
                    '201': {'description': 'Producto creado', 'content': {'application/json': {'schema': 'SuccessResponse'}}},
                    '400': {'description': 'Datos inválidos'},
                },
            ),
        ),
    )

    spec.path(
        path='/api/products/{id}',
        operations=dict(
            get=dict(
                tags=['Productos'],
                summary='Obtener producto',
                security=[{'bearer_jwt': []}],
                parameters=[{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                responses={
                    '200': {'description': 'Producto con modificadores'},
                    '404': {'description': 'No encontrado'},
                },
            ),
            put=dict(
                tags=['Productos'],
                summary='Actualizar producto',
                security=[{'bearer_jwt': []}],
                parameters=[{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                responses={
                    '200': {'description': 'Producto actualizado'},
                    '400': {'description': 'Datos inválidos'},
                    '404': {'description': 'No encontrado'},
                },
            ),
            delete=dict(
                tags=['Productos'],
                summary='Eliminar producto',
                security=[{'bearer_jwt': []}],
                parameters=[{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                responses={
                    '200': {'description': 'Producto eliminado'},
                    '404': {'description': 'No encontrado'},
                },
            ),
        ),
    )

    spec.path(
        path='/api/products/{id}/modifiers',
        operations=dict(
            get=dict(
                tags=['Productos - Modificadores'],
                summary='Listar modificadores de un producto',
                security=[{'bearer_jwt': []}],
                parameters=[{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                responses={'200': {'description': 'Lista de modificadores'}},
            ),
            post=dict(
                tags=['Productos - Modificadores'],
                summary='Crear modificador',
                security=[{'bearer_jwt': []}],
                parameters=[{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                responses={
                    '201': {'description': 'Modificador creado'},
                    '400': {'description': 'Datos inválidos'},
                },
            ),
        ),
    )

    # ── Categories ─────────────────────────────────────────────────────

    spec.path(
        path='/api/categories',
        operations=dict(
            get=dict(
                tags=['Categorías'],
                summary='Listar categorías',
                security=[{'bearer_jwt': []}],
                responses={'200': {'description': 'Lista de categorías'}},
            ),
            post=dict(
                tags=['Categorías'],
                summary='Crear categoría',
                security=[{'bearer_jwt': []}],
                responses={'201': {'description': 'Categoría creada'}},
            ),
        ),
    )

    spec.path(
        path='/api/categories/{id}',
        operations=dict(
            put=dict(
                tags=['Categorías'],
                summary='Actualizar categoría',
                security=[{'bearer_jwt': []}],
                parameters=[{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                responses={'200': {'description': 'Categoría actualizada'}},
            ),
            delete=dict(
                tags=['Categorías'],
                summary='Eliminar categoría',
                security=[{'bearer_jwt': []}],
                parameters=[{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                responses={'200': {'description': 'Categoría eliminada'}},
            ),
        ),
    )

    # ── Orders ─────────────────────────────────────────────────────────

    spec.path(
        path='/api/orders',
        operations=dict(
            get=dict(
                tags=['Pedidos'],
                summary='Listar pedidos',
                security=[{'bearer_jwt': []}],
                parameters=[
                    {'name': 'status', 'in': 'query', 'schema': {'type': 'string'}, 'description': 'Filtrar por estado'},
                    {'name': 'date', 'in': 'query', 'schema': {'type': 'string'}, 'description': 'Filtrar por fecha (YYYY-MM-DD)'},
                ],
                responses={'200': {'description': 'Lista de pedidos'}},
            ),
        ),
    )

    spec.path(
        path='/api/orders/create',
        operations=dict(
            post=dict(
                tags=['Pedidos'],
                summary='Crear pedido (público)',
                description='Crea un pedido desde el menú público. Sin autenticación, pero con rate limiting.',
                requestBody=dict(required=True, content={'application/json': {'schema': 'OrderCreate'}}),
                responses={
                    '201': {'description': 'Pedido creado'},
                    '429': {'description': 'Rate limit excedido', 'content': {'application/json': {'schema': 'ErrorResponse'}}},
                },
            ),
        ),
    )

    # ── Tables ─────────────────────────────────────────────────────────

    spec.path(
        path='/api/tables',
        operations=dict(
            get=dict(
                tags=['Mesas'],
                summary='Listar mesas',
                security=[{'bearer_jwt': []}],
                responses={'200': {'description': 'Lista de mesas'}},
            ),
            post=dict(
                tags=['Mesas'],
                summary='Crear mesa',
                security=[{'bearer_jwt': []}],
                responses={'201': {'description': 'Mesa creada'}},
            ),
        ),
    )

    spec.path(
        path='/api/tables/{id}',
        operations=dict(
            put=dict(
                tags=['Mesas'],
                summary='Actualizar mesa',
                security=[{'bearer_jwt': []}],
                parameters=[{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                responses={'200': {'description': 'Mesa actualizada'}},
            ),
            delete=dict(
                tags=['Mesas'],
                summary='Eliminar mesa',
                security=[{'bearer_jwt': []}],
                parameters=[{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}],
                responses={'200': {'description': 'Mesa eliminada'}},
            ),
        ),
    )

    # ── Tokens ─────────────────────────────────────────────────────────

    spec.path(
        path='/api/tokens/status',
        operations=dict(
            get=dict(
                tags=['Tokens AI'],
                summary='Estado del wallet de tokens',
                description='Requiere JWT de Clerk o API Key.',
                security=[{'bearer_jwt': []}, {'api_key': []}],
                responses={
                    '200': {'description': 'Estado del wallet', 'content': {'application/json': {'schema': 'AITokenWallet'}}},
                    '401': {'description': 'No autorizado'},
                },
            ),
        ),
    )

    spec.path(
        path='/api/tokens/consume',
        operations=dict(
            post=dict(
                tags=['Tokens AI'],
                summary='Consumir un token',
                description='Consume 1 token del wallet. Usado por Scanner IA.',
                security=[{'bearer_jwt': []}, {'api_key': []}],
                responses={
                    '200': {'description': 'Token consumido'},
                    '403': {'description': 'Sin tokens disponibles', 'content': {'application/json': {'schema': 'ErrorResponse'}}},
                },
            ),
        ),
    )

    spec.path(
        path='/api/tokens/topup/initiate',
        operations=dict(
            post=dict(
                tags=['Tokens AI'],
                summary='Iniciar compra de tokens',
                description='Crea una preferencia de pago en Mercado Pago.',
                security=[{'bearer_jwt': []}],
                responses={
                    '200': {'description': 'URL de checkout generada'},
                    '403': {'description': 'Usuarios trial no pueden comprar tokens'},
                },
            ),
        ),
    )

    # ── Public / Menu ─────────────────────────────────────────────────

    spec.path(
        path='/api/public/menu/{slug}',
        operations=dict(
            get=dict(
                tags=['Menú Público'],
                summary='Obtener menú público',
                description='Menú público del restaurante. No requiere autenticación.',
                parameters=[{'name': 'slug', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                responses={
                    '200': {'description': 'Menú del restaurante'},
                    '404': {'description': 'Restaurante no encontrado'},
                },
            ),
        ),
    )


# ─── Routes ─────────────────────────────────────────────────────────────

@api_docs_bp.route('/spec.json')
def openapi_spec():
    """Sirve el archivo OpenAPI spec en formato JSON."""
    spec = _build_spec()
    return Response(
        json.dumps(spec.to_dict(), indent=2, ensure_ascii=False),
        mimetype='application/json',
    )


@api_docs_bp.route('/')
def swagger_ui():
    """Sirve la interfaz Swagger UI para explorar la API."""
    _build_spec()  # ensure spec is built (swagger UI will fetch spec.json)
    return render_template('common/swagger_ui.html')
