from app import create_app
from sqlalchemy import inspect
from app.models import db

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    print(f"Table 'restaurants' exists: {inspector.has_table('restaurants')}")
