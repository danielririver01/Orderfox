from werkzeug.security import generate_password_hash

password_hash = generate_password_hash("Test1234")
print(password_hash)
