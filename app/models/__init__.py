"""
app/models/ — Paquete de modelos SQLAlchemy dividido por dominio.

Uso: from app.models import db, User, Restaurant, ...
     from app.models import db as _db  (conftest pattern)
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

from .core import AwareDateTime, Restaurant, User, Category, Product, Modifier, Table  # noqa: F401, E402
from .business import Business  # listeners del puente Restaurant↔Business quedan registrados
from .orders import Order, OrderItem, OrderEvent, OrderCounter  # noqa: F401, E402
from .cash import CashRegister  # noqa: F401, E402
from .ai import CopilotConversation, CopilotMessage, CopilotBusinessEvent, AILlmCall, PlatformBenchmark  # noqa: F401, E402
from .tokens import AITokenWallet, AITokenTransaction  # noqa: F401, E402
from .rewards import (  # noqa: F401, E402
    PreRegistration, TrialHistory, Expense,
    RewardClaim, UserAchievement, Streak, DiscountCoupon,
)
from .reservations import Reservation, ReservationSettings  # noqa: F401, E402

# Alias multi-vertical: el código NUEVO habla de Tenant/Business; Restaurant
# queda como el perfil del vertical restaurante (ver app/models/business.py).
Tenant = Business

__all__ = [
    'AILlmCall',
    'AITokenTransaction',
    'AITokenWallet',
    'AwareDateTime',
    'Business',
    'CashRegister',
    'Category',
    'CopilotBusinessEvent',
    'CopilotConversation',
    'CopilotMessage',
    'DiscountCoupon',
    'Expense',
    'Modifier',
    'Order',
    'OrderCounter',
    'OrderEvent',
    'OrderItem',
    'PlatformBenchmark',
    'PreRegistration',
    'Product',
    'Reservation',
    'ReservationSettings',
    'Restaurant',
    'RewardClaim',
    'Streak',
    'Table',
    'Tenant',
    'TrialHistory',
    'User',
    'UserAchievement',
    'db',
    'migrate',
]
