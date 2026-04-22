from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        print("Intentando limpiar tablas fantasma...")
        # Desactivamos checks de llaves foráneas para que no chille al borrar
        db.session.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        
        db.session.execute(text("DROP TABLE IF EXISTS ai_token_transactions;"))
        db.session.execute(text("DROP TABLE IF EXISTS ai_token_wallets;"))
        
        db.session.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        db.session.commit()
        print("✅ Tablas eliminadas con éxito. Ahora puedes correr flask db upgrade.")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error al limpiar: {e}")