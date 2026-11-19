from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

import user
from database import get_session
from main import app

client = TestClient(app)

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

client = TestClient(app)

PASSWORD = "supersecret12345"


def override_get_session():
    with Session(test_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def reset_db():
    SQLModel.metadata.drop_all(test_engine)
    SQLModel.metadata.create_all(test_engine)
    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.pop(get_session, None)
    SQLModel.metadata.drop_all(test_engine)


def create_user(username="ivan", email="ivan@example.com", password=PASSWORD):
    r = client.post("/users/", json={
        "username": username,
        "email": email,
        "password": password,
    })
    assert r.status_code == 201
    return r.json()


def auth_headers(username="ivan", password=PASSWORD):
    r = client.post("/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_admin(user_id: str) -> None:
    with Session(test_engine) as session:
        db_user = session.get(user.UserModel, UUID(user_id))
        db_user.role = user.Role.admin
        session.add(db_user)
        session.commit()


def admin_headers():
    u = create_user(username="admin1", email="admin1@example.com")
    make_admin(u["id"])
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

    