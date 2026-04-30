from app import create_app
from app.models import db, User

app = create_app()
with app.app_context():
    users = User.query.all()
    print("Usuarios en BD:")
    for u in users:
        print(f"ID: {u.id}, Email: {u.email}, clerk_id: {u.clerk_id}")
