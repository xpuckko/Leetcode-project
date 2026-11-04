from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import user
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    user.users_db.clear()
    yield
    user.users_db.clear()


def create_user(username="ivan", email="ivan@example.com", password="supersecret1"):
    r = client.post("/users/", json={
        "username": username,
        "email": email,
        "password": password,
    })
    assert r.status_code == 201
    return r.json()


def auth_headers(username="ivan", password="supersecret1"):
    r = client.post("/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_admin(user_id: str) -> None:
    user.users_db[UUID(user_id)]["role"] = user.Role.admin


def test_get_own_user_does_not_leak_password_hash():
    u = create_user()
    r = client.get(f"/users/{u['id']}", headers=auth_headers())
    assert r.status_code == 200
    assert "password_hash" not in r.json()


def test_get_me_returns_own_profile():
    u = create_user()
    r = client.get("/users/me", headers=auth_headers())
    assert r.status_code == 200
    assert r.json()["id"] == u["id"]


def test_get_me_without_token_is_rejected():
    r = client.get("/users/me")
    assert r.status_code in (401, 403)


def test_get_other_user_returns_403():
    create_user()
    p = create_user(username="petar", email="petar@example.com")
    r = client.get(f"/users/{p['id']}", headers=auth_headers("ivan"))
    assert r.status_code == 403


def test_get_invalid_uuid_returns_422():
    create_user()
    r = client.get("/users/5", headers=auth_headers())
    assert r.status_code == 422


def test_list_users_as_regular_user_returns_403():
    create_user()
    r = client.get("/users/", headers=auth_headers())
    assert r.status_code == 403


def test_list_users_as_admin_does_not_leak_password_hash():
    u = create_user()
    make_admin(u["id"])
    r = client.get("/users/", headers=auth_headers())
    assert r.status_code == 200
    assert all("password_hash" not in x for x in r.json())


def test_admin_gets_404_for_missing_user():
    u = create_user()
    make_admin(u["id"])
    r = client.get(f"/users/{uuid4()}", headers=auth_headers())
    assert r.status_code == 404


def test_patch_user_changes_email():
    u = create_user()
    r = client.patch(f"/users/{u['id']}", json={"email": "new@example.com"},
                     headers=auth_headers())
    assert r.status_code == 200
    assert r.json()["email"] == "new@example.com"
    assert r.json()["username"] == "ivan"


def test_patch_user_does_not_leak_password_hash():
    u = create_user()
    r = client.patch(f"/users/{u['id']}", json={"password": "newsecret123"},
                     headers=auth_headers())
    assert r.status_code == 200
    assert "password_hash" not in r.json()
    assert "password" not in r.json()


def test_patch_user_changes_password_hash():
    u = create_user()
    uid = UUID(u["id"])
    old_hash = user.users_db[uid]["password_hash"]
    client.patch(f"/users/{u['id']}", json={"password": "newsecret123"},
                 headers=auth_headers())
    new_hash = user.users_db[uid]["password_hash"]
    assert new_hash != old_hash
    assert user.verify_password("newsecret123", new_hash)


def test_patch_other_user_returns_403():
    create_user()
    p = create_user(username="petar", email="petar@example.com")
    r = client.patch(f"/users/{p['id']}", json={"email": "x@example.com"},
                     headers=auth_headers("ivan"))
    assert r.status_code == 403


def test_patch_missing_user_returns_403_for_regular_user():
    create_user()
    r = client.patch(f"/users/{uuid4()}", json={"email": "new@example.com"},
                     headers=auth_headers())
    assert r.status_code == 403


def test_patch_missing_user_returns_404_for_admin():
    u = create_user()
    make_admin(u["id"])
    r = client.patch(f"/users/{uuid4()}", json={"email": "new@example.com"},
                     headers=auth_headers())
    assert r.status_code == 404


def test_patch_duplicate_username_returns_409():
    create_user()
    p = create_user(username="petar", email="petar@example.com")
    r = client.patch(f"/users/{p['id']}", json={"username": "ivan"},
                     headers=auth_headers("petar"))
    assert r.status_code == 409


def test_patch_duplicate_email_returns_409():
    create_user()
    p = create_user(username="petar", email="petar@example.com")
    r = client.patch(f"/users/{p['id']}", json={"email": "ivan@example.com"},
                     headers=auth_headers("petar"))
    assert r.status_code == 409


def test_patch_same_username_on_self_is_allowed():
    u = create_user()
    r = client.patch(f"/users/{u['id']}", json={"username": "ivan"},
                     headers=auth_headers())
    assert r.status_code == 200


def test_patch_short_password_returns_422():
    u = create_user()
    r = client.patch(f"/users/{u['id']}", json={"password": "short"},
                     headers=auth_headers())
    assert r.status_code == 422


def test_delete_user_success():
    u = create_user()
    headers = auth_headers()
    r = client.delete(f"/users/{u['id']}", headers=headers)
    assert r.status_code == 204
    assert client.get("/users/me", headers=headers).status_code == 401


def test_delete_other_user_returns_403():
    create_user()
    p = create_user(username="petar", email="petar@example.com")
    r = client.delete(f"/users/{p['id']}", headers=auth_headers("ivan"))
    assert r.status_code == 403


def test_delete_missing_user_returns_404_for_admin():
    u = create_user()
    make_admin(u["id"])
    r = client.delete(f"/users/{uuid4()}", headers=auth_headers())
    assert r.status_code == 404


def test_register_emails_differing_only_in_case_conflict():
    create_user(email="ivan@example.com")
    r = client.post("/users/", json={
        "username": "petar",
        "email": "IVAN@example.com",
        "password": "supersecret1",
    })
    assert r.status_code == 409