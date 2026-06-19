from datetime import datetime, timezone
from marshmallow import Schema, fields, validate, post_load


# ─── Response Envelope Schemas ─────────────────────────────────────────

class SuccessResponse(Schema):
    success = fields.Boolean(dump_default=True)
    message = fields.String(dump_default='Operación exitosa')
    data = fields.Dict(dump_default={})

class ErrorResponse(Schema):
    success = fields.Boolean(dump_default=False)
    error_code = fields.String()
    message = fields.String()

class PaginationMeta(Schema):
    page = fields.Integer()
    per_page = fields.Integer()
    total = fields.Integer()
    pages = fields.Integer()

class PaginatedData(Schema):
    pagination = fields.Nested(PaginationMeta)


# ─── Model Schemas ─────────────────────────────────────────────────────

class RestaurantSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String()
    slug = fields.String()
    whatsapp_phone = fields.String()
    plan_type = fields.String()
    is_active = fields.Boolean()
    is_open = fields.Boolean()

class UserSchema(Schema):
    id = fields.Integer(dump_only=True)
    username = fields.String()
    email = fields.Email()
    restaurant_id = fields.Integer(dump_default=None)

class CategorySchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String()
    description = fields.String(dump_default=None)
    sort_order = fields.Integer()
    is_active = fields.Boolean()
    image_url = fields.String(dump_default=None)
    products_count = fields.Integer(dump_default=0)

class ModifierSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String()
    extra_price = fields.Integer()
    is_active = fields.Boolean()

class ProductSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String()
    description = fields.String(dump_default=None)
    price = fields.Integer()
    is_active = fields.Boolean()
    image_url = fields.String(dump_default=None)
    category_id = fields.Integer()
    category_name = fields.String(dump_default=None)
    modifiers = fields.List(fields.Nested(ModifierSchema), dump_default=[])
    modifiers_count = fields.Integer(dump_default=0)
    created_at = fields.DateTime(dump_default=None)

class ProductCreate(Schema):
    name = fields.String(required=True)
    description = fields.String(dump_default='')
    price = fields.Integer(required=True)
    category_id = fields.Integer(required=True)
    is_active = fields.Boolean(dump_default=True)

class OrderItemSchema(Schema):
    id = fields.Integer(dump_only=True)
    product_name = fields.String()
    product_price = fields.Integer()
    quantity = fields.Integer()
    modifiers_snapshot = fields.String(dump_default=None)
    subtotal = fields.Integer()

class OrderSchema(Schema):
    id = fields.Integer(dump_only=True)
    order_number = fields.String()
    customer_name = fields.String(dump_default=None)
    customer_phone = fields.String(dump_default=None)
    status = fields.String()
    total = fields.Integer()
    notes = fields.String(dump_default=None)
    table_id = fields.Integer(dump_default=None)
    items = fields.List(fields.Nested(OrderItemSchema), dump_default=[])
    created_at = fields.DateTime()

class OrderCreate(Schema):
    restaurant_id = fields.Integer(required=True)
    table_id = fields.Integer(dump_default=None)
    customer_name = fields.String(dump_default='')
    customer_phone = fields.String(dump_default='')
    notes = fields.String(dump_default='')
    cart = fields.List(fields.Dict, required=True)
    total = fields.Integer(required=True)

class TableSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String()
    qr_code = fields.String(dump_default=None)
    is_active = fields.Boolean()

class AITokenWalletSchema(Schema):
    is_elite = fields.Boolean()
    plan_limit = fields.Integer(dump_default=None)
    plan_tokens = fields.Integer()
    extra_tokens = fields.Integer()
    total_available = fields.Raw()  # int o float('inf')
    tokens_used = fields.Integer()
    usage_percent = fields.Raw(dump_default=None)
    can_scan = fields.Boolean()
    plan_type = fields.String()
    reset_at = fields.String(dump_default=None)

class LoginRequest(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=1))

class SyncClerkRequest(Schema):
    clerk_id = fields.String(required=True)
    email = fields.Email(required=True)
    username = fields.String(required=True)
    name = fields.String(dump_default='')



