"""
run_auto_tests.py — Automated security tests (IDOR, NoAuth, Fuzzing)
Run: python tests/security/burp/run_auto_tests.py
Requires: Flask server at localhost:5000
"""
import requests
import json
import re
import sys

BASE = 'http://localhost:5000'
API = f'{BASE}/api'

s = requests.Session()
results = []

def log(test, status, detail):
    icon = {'OK ': 'PASS', 'KO ': 'FAIL', 'WW:': 'WARN', 'II:': 'INFO'}.get(status[:3], 'INFO')
    label = f'[{icon}]'
    print(f'  {label} {test}: {detail}')
    results.append({'test': test, 'status': status, 'detail': detail})

def test_unauthorized(endpoint, method='GET', data=None):
    """Test 4: Access without authentication"""
    url = f'{API}{endpoint}' if endpoint.startswith('/products') or endpoint.startswith('/orders') or endpoint.startswith('/categories') or endpoint.startswith('/tables') else f'{BASE}{endpoint}'
    try:
        r = requests.get(url, timeout=5, allow_redirects=False) if method == 'GET' else requests.post(url, json=data or {}, timeout=5, allow_redirects=False)
        if r.status_code in (401, 403):
            log(f'NoAuth {method} {endpoint}', 'OK ', f'Status {r.status_code}')
            return True
        elif r.status_code in (301, 302):
            # Redirect to login = effectively requires auth
            log(f'NoAuth {method} {endpoint}', 'OK ', f'Status {r.status_code} (redirect to login)')
            return True
        log(f'NoAuth {method} {endpoint}', 'KO ', f'Status {r.status_code} (expected 401/403/302)')
        return True
    except Exception as e:
        log(f'NoAuth {method} {endpoint}', 'WW:', str(e))
        return False

def test_idor():
    """Test 1: IDOR — access another restaurant's data"""
    # Get own restaurant_id from token (stress user = restaurant 5)
    r = s.get(f'{API}/categories', timeout=5)
    own_id = None
    if r.status_code == 200:
        data = r.json()
        own_id = data.get('data', {}).get('restaurant_id')
        log('IDOR categories own', 'OK ', f'Own restaurant: {r.status_code}')
    else:
        log('IDOR categories own', 'II:', f'Status {r.status_code}')

    # Try another restaurant (3 or 4)
    other_id = 3 if own_id != 3 else 4
    r = s.get(f'{API}/categories?restaurant_id={other_id}', timeout=5)
    if r.status_code in (401, 403, 404):
        log('IDOR categories other', 'OK ', f'Other restaurant_id={other_id}: {r.status_code}')
    elif r.status_code == 200:
        data = r.json()
        resp_rid = data.get('data', {}).get('restaurant_id')
        if resp_rid == own_id:
            log('IDOR categories other', 'WW:', f'200 but filtered to own restaurant ({resp_rid}) - OK')
        else:
            log('IDOR categories other', 'KO ', f'200 with restaurant_id={resp_rid} (possible IDOR)')
    else:
        log('IDOR categories other', 'II:', f'Status {r.status_code}')

    r = s.get(f'{API}/products?restaurant_id={other_id}', timeout=5)
    if r.status_code in (401, 403, 404):
        log('IDOR products other', 'OK ', f'Other restaurant_id={other_id}: {r.status_code}')
    elif r.status_code == 200:
        log('IDOR products other', 'WW:', f'Status 200 - check manually')
    else:
        log('IDOR products other', 'II:', f'Status {r.status_code}')

    r = s.get(f'{API}/orders?restaurant_id={other_id}', timeout=5)
    if r.status_code in (401, 403, 404):
        log('IDOR orders other', 'OK ', f'Other restaurant_id={other_id}: {r.status_code}')
    elif r.status_code == 200:
        log('IDOR orders other', 'WW:', f'Status 200 - check manually')
    else:
        log('IDOR orders other', 'II:', f'Status {r.status_code}')

    r = s.post(f'{API}/orders', json={'customer_name': 'IDOR Test', 'items': [], 'restaurant_id': other_id}, timeout=5)
    if r.status_code in (401, 403, 404):
        log('IDOR create order other', 'OK ', f'Create order restaurant_id={other_id}: {r.status_code}')
    elif r.status_code == 200:
        log('IDOR create order other', 'KO ', f'Create order restaurant_id={other_id}: 200')
    else:
        log('IDOR create order other', 'II:', f'Status {r.status_code}')

def test_fuzzing():
    """Test 5: Parameter fuzzing"""
    tests = [
        ('page=-1', '/products?page=-1'),
        ('page=abc', '/products?page=abc'),
        ('limit=999999', '/products?limit=999999'),
        ('limit=-1', '/products?limit=-1'),
        ('limit=abc', '/products?limit=abc'),
        ('id=999999', '/categories?id=999999'),
        ('id=abc', '/categories?id=abc'),
        ('id=1 OR 1=1', '/categories?id=1+OR+1=1'),
    ]
    for name, path in tests:
        try:
            r = s.get(f'{API}{path}', timeout=5, allow_redirects=False)
            if r.status_code == 500:
                log(f'Fuzz {name}', 'KO ', f'Status 500 - possible crash')
            elif r.status_code == 200:
                log(f'Fuzz {name}', 'OK ', f'Status 200 (normal)')
            elif r.status_code in (400, 422, 404):
                log(f'Fuzz {name}', 'OK ', f'Status {r.status_code} (rejected correctly)')
            else:
                log(f'Fuzz {name}', 'II:', f'Status {r.status_code}')
        except Exception as e:
            log(f'Fuzz {name}', 'WW:', str(e))

def main():
    print('=' * 55)
    print('  Velzia Automated Security Tests')
    print(f'  URL: {BASE}')
    print('=' * 55)

    print('\n[Test 4] Routes without auth')
    print('-' * 40)
    test_unauthorized('/products')
    test_unauthorized('/orders')
    test_unauthorized('/categories', 'POST', {'name': 'test'})
    test_unauthorized('/tables')
    for path in ['/insights/api/conversations/1', '/insights/api/events/pending']:
        test_unauthorized(path)

    print('\n[Login]')
    print('-' * 40)
    login_r = s.post(f'{BASE}/api/auth/login', json={
        'email': 'stress@velzia.co',
        'password': 'stress1234'
    }, timeout=5)
    if login_r.status_code == 200:
        data = login_r.json()
        token = data.get('data', {}).get('access_token')
        if token:
            s.headers.update({'Authorization': f'Bearer {token}'})
        log('Login API', 'OK ', 'Success (stress user)')
    else:
        log('Login API', 'KO ', f'Status {login_r.status_code}')

    print('\n[Test 1] IDOR')
    print('-' * 40)
    test_idor()

    print('\n[Test 5] Fuzzing')
    print('-' * 40)
    test_fuzzing()

    print('\n' + '=' * 55)
    print('  SUMMARY')
    print('=' * 55)
    passed = sum(1 for r in results if r['status'].startswith('OK'))
    failed = sum(1 for r in results if r['status'].startswith('KO'))
    warned = sum(1 for r in results if r['status'].startswith('WW'))
    total = len(results)
    print(f'  PASS: {passed}/{total}')
    print(f'  FAIL: {failed}/{total}')
    print(f'  WARN: {warned}/{total}')
    if failed:
        print('\n  Critical findings:')
        for r in results:
            if r['status'].startswith('KO'):
                print(f'    - {r["test"]}: {r["detail"]}')
    print()

if __name__ == '__main__':
    main()
