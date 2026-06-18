from werkzeug.security import generate_password_hash
import csv

hashed_pw = generate_password_hash('admin123')

with open('users.csv', mode='w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['username', 'password', 'role']) # Header
    writer.writerow(['admin', hashed_pw, 'admin'])    # The Admin user

print("✅ users.csv has been reset!")
print(f"Your new hash is: {hashed_pw}")