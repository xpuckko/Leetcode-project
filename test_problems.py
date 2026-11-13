from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

import user
from database import get_session
from main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_db():
    user.users_db.clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.clear()
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


def admin_headers():
    u = create_user(username="admin1", email="admin1@example.com")
    user.users_db[UUID(u["id"])]["role"] = user.Role.admin
    return auth_headers("admin1")


def test_create_and_get_problem() -> None:
    admin = admin_headers()
    payload = {
        "title": "Two Sum",
        "description": "Find two numbers that add up to target",
        "time_limit_sec": 1.0,
        "memory_limit_kb": 65536,
        "is_visible": True,
        "difficulty": "easy",
    }
    response = client.post("/problems/", json=payload, headers=admin)
    assert response.status_code == 201
    created = response.json()

    response = client.get(f"/problems/{created['id']}", headers=admin)
    assert response.status_code == 200
    assert response.json()["title"] == "Two Sum"

def test_get_missing_problem_returns_404() -> None:
    response = client.get(f"/problems/{uuid4()}", headers=admin_headers())
    assert response.status_code == 404