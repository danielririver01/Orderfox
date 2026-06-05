from app.models import db, Table, Order


class TableService:
    """Business logic for Table operations.
    Shared by web routes (tables_bp) and API routes (api_tables_bp).
    QR generation remains in routes (coupled to request context).
    """

    @staticmethod
    def get_tables(restaurant_id):
        """Return all tables ordered by created_at."""
        return Table.query.filter_by(restaurant_id=restaurant_id).order_by(Table.created_at).all()

    @staticmethod
    def get_table(restaurant_id, table_id):
        """Return Table or None."""
        return Table.query.filter_by(id=table_id, restaurant_id=restaurant_id).first()

    @staticmethod
    def create_table(restaurant_id, name, qr_code=None):
        """
        Create a new table. Returns (Table, None) or (None, error_message).
        Name is required.
        """
        if not name or not name.strip():
            return None, 'El nombre de la mesa es requerido'
        table = Table(
            restaurant_id=restaurant_id,
            name=name.strip(),
            qr_code=qr_code,
            is_active=True
        )
        db.session.add(table)
        db.session.commit()
        return table, None

    @staticmethod
    def delete_table(table, check_active_orders=False):
        """
        Delete a table. Returns (True, None) or (False, error_message).
        If check_active_orders is True, blocks deletion if table has pending orders.
        """
        if check_active_orders:
            active_count = Order.query.filter_by(
                table_id=table.id,
                restaurant_id=table.restaurant_id,
                status='pending'
            ).count()
            if active_count > 0:
                return False, f'No se puede eliminar porque tiene {active_count} orden(es) activa(s)'
        db.session.delete(table)
        db.session.commit()
        return True, None

    @staticmethod
    def get_active_orders_count(restaurant_id, table_id):
        """Return count of pending orders for a table."""
        return Order.query.filter_by(
            table_id=table_id,
            restaurant_id=restaurant_id,
            status='pending'
        ).count()
