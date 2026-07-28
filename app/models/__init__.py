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
from .orders import Order, OrderItem, OrderCounter  # noqa: F401, E402
from .ai import CopilotConversation, CopilotMessage, CopilotBusinessEvent  # noqa: F401, E402
from .tokens import AITokenWallet, AITokenTransaction  # noqa: F401, E402
from .rewards import (  # noqa: F401, E402
    PreRegistration, TrialHistory, Expense,
    RewardClaim, UserAchievement, Streak, DiscountCoupon,
)
