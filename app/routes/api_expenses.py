from flask import Blueprint, jsonify, request
from datetime import date, datetime, timedelta
from sqlalchemy import func
from app import db
from app.models import Expense
from app.utils.jwt_auth import jwt_login_required, jwt_active_required, get_current_restaurant_jwt

api_expenses_bp = Blueprint('api_expenses', __name__, url_prefix='/api/expenses')


@api_expenses_bp.route('', methods=['GET'])
@jwt_login_required
@jwt_active_required
def list_expenses():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    
    range_param = request.args.get('range', 'today')
    category = request.args.get('category')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = Expense.query.filter_by(restaurant_id=restaurant.id)
    
    today = date.today()
    if range_param == 'today':
        query = query.filter(Expense.date == today)
    elif range_param == 'week':
        week_start = today - timedelta(days=today.weekday())
        query = query.filter(Expense.date >= week_start)
    elif range_param == 'month':
        month_start = today.replace(day=1)
        query = query.filter(Expense.date >= month_start)
    
    if category:
        query = query.filter_by(category=category)
    
    query = query.order_by(Expense.date.desc(), Expense.created_at.desc())
    total = query.count()
    expenses = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return jsonify({
        'success': True,
        'data': {
            'expenses': [
                {
                    'id': e.id,
                    'description': e.description,
                    'amount': e.amount,
                    'category': e.category,
                    'date': e.date.isoformat(),
                    'created_at': e.created_at.isoformat() if e.created_at else None,
                }
                for e in expenses
            ],
            'pagination': {
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page,
            }
        }
    })


@api_expenses_bp.route('', methods=['POST'])
@jwt_login_required
@jwt_active_required
def create_expense():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400
    
    description = data.get('description', '').strip()
    amount = data.get('amount')
    category = data.get('category', 'otros')
    expense_date = data.get('date')
    
    if not description:
        return jsonify({'success': False, 'error': 'La descripcion es requerida'}), 400
    
    if not amount or not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({'success': False, 'error': 'El monto debe ser mayor a 0'}), 400
    
    valid_categories = ['ingredientes', 'servicios', 'personal', 'equipamiento', 'otros']
    if category not in valid_categories:
        return jsonify({'success': False, 'error': 'Categoria invalida'}), 400
    
    if expense_date:
        try:
            expense_date = date.fromisoformat(expense_date)
        except ValueError:
            return jsonify({'success': False, 'error': 'Fecha invalida'}), 400
    else:
        expense_date = date.today()
    
    expense = Expense(
        restaurant_id=restaurant.id,
        description=description,
        amount=int(amount),
        category=category,
        date=expense_date,
    )
    
    db.session.add(expense)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'data': {
            'id': expense.id,
            'description': expense.description,
            'amount': expense.amount,
            'category': expense.category,
            'date': expense.date.isoformat(),
            'created_at': expense.created_at.isoformat() if expense.created_at else None,
        }
    }), 201


@api_expenses_bp.route('/<int:id>', methods=['PUT'])
@jwt_login_required
@jwt_active_required
def update_expense(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    
    expense = Expense.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not expense:
        return jsonify({'success': False, 'error': 'Gasto no encontrado'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos requeridos'}), 400
    
    if 'description' in data:
        expense.description = data['description'].strip()
    if 'amount' in data:
        if not isinstance(data['amount'], (int, float)) or data['amount'] <= 0:
            return jsonify({'success': False, 'error': 'El monto debe ser mayor a 0'}), 400
        expense.amount = int(data['amount'])
    if 'category' in data:
        valid_categories = ['ingredientes', 'servicios', 'personal', 'equipamiento', 'otros']
        if data['category'] not in valid_categories:
            return jsonify({'success': False, 'error': 'Categoria invalida'}), 400
        expense.category = data['category']
    if 'date' in data:
        try:
            expense.date = date.fromisoformat(data['date'])
        except ValueError:
            return jsonify({'success': False, 'error': 'Fecha invalida'}), 400
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'data': {
            'id': expense.id,
            'description': expense.description,
            'amount': expense.amount,
            'category': expense.category,
            'date': expense.date.isoformat(),
            'created_at': expense.created_at.isoformat() if expense.created_at else None,
        }
    })


@api_expenses_bp.route('/<int:id>', methods=['DELETE'])
@jwt_login_required
@jwt_active_required
def delete_expense(id):
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    
    expense = Expense.query.filter_by(id=id, restaurant_id=restaurant.id).first()
    if not expense:
        return jsonify({'success': False, 'error': 'Gasto no encontrado'}), 404
    
    db.session.delete(expense)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Gasto eliminado'
    })


@api_expenses_bp.route('/summary', methods=['GET'])
@jwt_login_required
@jwt_active_required
def summary():
    restaurant = get_current_restaurant_jwt()
    if not restaurant:
        return jsonify({'success': False, 'error': 'Restaurante no encontrado'}), 404
    
    range_param = request.args.get('range', 'today')
    today = date.today()
    
    query = Expense.query.filter_by(restaurant_id=restaurant.id)
    
    if range_param == 'today':
        query = query.filter(Expense.date == today)
    elif range_param == 'week':
        week_start = today - timedelta(days=today.weekday())
        query = query.filter(Expense.date >= week_start)
    elif range_param == 'month':
        month_start = today.replace(day=1)
        query = query.filter(Expense.date >= month_start)
    
    total = query.with_entities(func.sum(Expense.amount)).scalar() or 0
    
    by_category = query.with_entities(
        Expense.category,
        func.sum(Expense.amount)
    ).group_by(Expense.category).all()
    
    return jsonify({
        'success': True,
        'data': {
            'total': total,
            'range': range_param,
            'by_category': {cat: amount for cat, amount in by_category},
        }
    })
