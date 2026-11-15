def test_user_registration_success(client):
    res = client.post("/api/auth/register", json={
        "email": "test.elder@care.org",
        "password": "SecurePassword99!",
        "full_name": "Eleanor Vance",
        "phone": "+1-555-4321",
        "role": "elderly"
    })
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "test.elder@care.org"
    assert data["user"]["role"] == "elderly"
    assert data["user"]["full_name"] == "Eleanor Vance"

def test_duplicate_registration_fails(client):
    payload = {
        "email": "duplicate@care.org",
        "password": "Password123!",
        "full_name": "Original User",
        "role": "family"
    }
    res1 = client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"]

def test_login_success(client):
    # Register
    client.post("/api/auth/register", json={
        "email": "login.test@care.org",
        "password": "MySecretPassword123",
        "full_name": "Login Tester",
        "role": "caretaker"
    })

    # Login with valid credentials
    res = client.post("/api/auth/login", json={
        "email": "login.test@care.org",
        "password": "MySecretPassword123"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "caretaker"

def test_login_invalid_password_fails(client):
    client.post("/api/auth/register", json={
        "email": "wrongpwd@care.org",
        "password": "CorrectPassword123",
        "full_name": "Wrong Tester",
        "role": "elderly"
    })

    res = client.post("/api/auth/login", json={
        "email": "wrongpwd@care.org",
        "password": "IncorrectPassword"
    })
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]

def test_login_nonexistent_user_fails(client):
    res = client.post("/api/auth/login", json={
        "email": "ghost@care.org",
        "password": "Password123!"
    })
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]

def test_auth_me_endpoint(client, elderly_user_token):
    token = elderly_user_token["token"]
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "elderly.alice@care.org"
    assert data["role"] == "elderly"

def test_unauthenticated_request_fails(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401
