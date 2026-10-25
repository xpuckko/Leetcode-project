import pytest
from fastapi.testclient import TestClient

import user
from main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_db():
    user.users_db.clear()
    user.next_user_id = 1
    yield

def test_get_user_does_not_leak_password_hash() -> None:
    client.post("/users/", json={
        "username": "ivan",
        "email": "ivan@example.com",
        "password": "supersecret1",
    })
    r = client.get("/users/1")
    assert r.status_code == 200
    assert "password_hash" not in r.json()

def test_list_users_does_not_leak_password_hash() -> None:
    client.post("/users/", json={
        "username": "ivan",
        "email": "ivan@example.com",
        "password": "supersecret1",
    })
    r = client.get("/users/")
    assert all("password_hash" not in u for u in r.json())

def create_user(username="ivan", email="ivan@example.com", password="supersecret1"):
    return client.post("/users/", json={
        "username": username,
        "email": email,
        "password": password,
    })


def test_patch_user_changes_email():
    create_user()
    r = client.patch("/users/1", json={"email": "new@example.com"})
    assert r.status_code == 200
    assert r.json()["email"] == "new@example.com"
    assert r.json()["username"] == "ivan"


def test_patch_user_does_not_leak_password_hash():
    create_user()
    r = client.patch("/users/1", json={"password": "newsecret123"})
    assert r.status_code == 200
    assert "password_hash" not in r.json()
    assert "password" not in r.json()


def test_patch_user_changes_password_hash():
    create_user()
    old_hash = user.users_db[1]["password_hash"]
    client.patch("/users/1", json={"password": "newsecret123"})
    new_hash = user.users_db[1]["password_hash"]
    assert new_hash != old_hash
    assert user.verify_password("newsecret123", new_hash)


def test_patch_missing_user_returns_404():
    r = client.patch("/users/9999", json={"email": "new@example.com"})
    assert r.status_code == 404


def test_patch_duplicate_username_returns_409():
    create_user()
    create_user(username="petar", email="petar@example.com")
    r = client.patch("/users/2", json={"username": "ivan"})
    assert r.status_code == 409


def test_patch_duplicate_email_returns_409():
    create_user()
    create_user(username="petar", email="petar@example.com")
    r = client.patch("/users/2", json={"email": "ivan@example.com"})
    assert r.status_code == 409


def test_patch_same_username_on_self_is_allowed():
    create_user()
    r = client.patch("/users/1", json={"username": "ivan"})
    assert r.status_code == 200


def test_patch_short_password_returns_422():
    create_user()
    r = client.patch("/users/1", json={"password": "short"})
    assert r.status_code == 422


def test_delete_user_success():
    create_user()
    r = client.delete("/users/1")
    assert r.status_code == 204
    assert client.get("/users/1").status_code == 404


def test_delete_missing_user_returns_404():
    r = client.delete("/users/9999")
    assert r.status_code == 404