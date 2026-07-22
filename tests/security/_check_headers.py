import requests
r = requests.get('http://localhost:5000/', timeout=10)
print('Status:', r.status_code)
print()
print('=== Security Headers ===')
checks = {
    'Content-Security-Policy': r.headers.get('Content-Security-Policy', 'MISSING'),
    'X-Frame-Options': r.headers.get('X-Frame-Options', 'MISSING'),
    'X-Content-Type-Options': r.headers.get('X-Content-Type-Options', 'MISSING'),
    'X-XSS-Protection': r.headers.get('X-XSS-Protection', 'MISSING'),
    'Referrer-Policy': r.headers.get('Referrer-Policy', 'MISSING'),
    'Permissions-Policy': r.headers.get('Permissions-Policy', 'MISSING'),
    'Server': r.headers.get('Server', 'REMOVED'),
}
for h, v in checks.items():
    ok = v != 'MISSING' if h != 'Server' else v == 'REMOVED'
    print(f'  {"OK" if ok else "MISSING"}  {h}: {v}')

print()
print('=== Cookie ===')
c = r.headers.get('Set-Cookie', 'NONE')
print(f'  SameSite: {"YES" if "SameSite" in c else "NO"}')
print(f'  HttpOnly: {"YES" if "HttpOnly" in c else "NO"}')
print(f'  Raw: {c[:200]}')
