import requests

# Тест регистрации
data = {
    'nickname': 'TestUser123',
    'phone': '+79123456789',
    'password': 'test123',
    'password_confirm': 'test123'
}

response = requests.post('http://localhost:5000/register', data=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.text[:500]}")