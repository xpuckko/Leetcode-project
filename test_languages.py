from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

import user
from database import get_session
from main import app
from database import SessionDep

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

def override_get_session():
    print("USING TEST DATABASE:", test_engine.url)
    with Session(test_engine) as session:
        yield session

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_db():
    SQLModel.metadata.drop_all(test_engine)
    SQLModel.metadata.create_all(test_engine)
    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.pop(get_session, None)
    SQLModel.metadata.drop_all(test_engine)

PASSWORD = "supersecret12345"


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
    u = create_user(username="admin", email="admin@example.com")
    make_admin(u["id"])
    return auth_headers("admin")


def create_language(headers, slug="python", name="Python", judge0_language_id=71, is_enabled=True):
    return client.post("/languages/", json={
        "slug": slug,
        "name": name,
        "judge0_language_id": judge0_language_id,
        "is_enabled": is_enabled,
    }, headers=headers)


def test_create_language_as_admin():
    r = create_language(admin_headers())
    assert r.status_code == 201
    assert r.json() == {
        "slug": "python",
        "name": "Python",
        "judge0_language_id": 71,
        "is_enabled": True,
    }


def test_create_language_as_regular_user_returns_403():
    create_user()
    r = create_language(auth_headers())
    assert r.status_code == 403


def test_create_duplicate_slug_returns_409():
    h = admin_headers()
    create_language(h)
    r = create_language(h, name="Other", judge0_language_id=99)
    assert r.status_code == 409


def test_create_duplicate_name_differing_only_in_case_returns_409():
    h = admin_headers()
    create_language(h)
    r = create_language(h, slug="python2", name="PYTHON", judge0_language_id=99)
    assert r.status_code == 409


def test_create_duplicate_judge0_id_returns_409():
    h = admin_headers()
    create_language(h)
    r = create_language(h, slug="python2", name="Python 2", judge0_language_id=71)
    assert r.status_code == 409


def test_create_invalid_slug_returns_422():
    r = create_language(admin_headers(), slug="BAD SLUG!")
    assert r.status_code == 422


def test_list_languages_hides_disabled_and_internal_fields():
    h = admin_headers()
    create_language(h)
    create_language(h, slug="java", name="Java", judge0_language_id=62, is_enabled=False)
    r = client.get("/languages/")
    assert r.status_code == 200
    assert r.json() == [{"slug": "python", "name": "Python"}]


def test_get_disabled_language_returns_404():
    created = create_language(admin_headers(), is_enabled=False)
    r = client.get("/languages/python")
    assert r.status_code == 404


def test_admin_list_includes_disabled_languages():
    h = admin_headers()
    create_language(h)
    create_language(h, slug="java", name="Java", judge0_language_id=62, is_enabled=False)
    r = client.get("/admin/languages/", headers=h)
    assert r.status_code == 200
    assert {l["slug"] for l in r.json()} == {"python", "java"}


def test_patch_language_changes_name_only():
    h = admin_headers()
    create_language(h)
    r = client.patch("/languages/python", json={"name": "Python 3"}, headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "Python 3"
    assert r.json()["judge0_language_id"] == 71


def test_patch_cannot_change_slug():
    h = admin_headers()
    create_language(h)
    r = client.patch("/languages/python", json={"slug": "hacked", "name": "Python 3"}, headers=h)
    assert r.status_code == 200
    assert r.json()["slug"] == "python"


def test_patch_duplicate_name_returns_409():
    h = admin_headers()
    first = create_language(h)
    second = create_language(h, slug="java", name="Java", judge0_language_id=62)
    r = client.patch("/languages/java", json={"name": "python"}, headers=h)
    assert r.status_code == 409


def test_patch_missing_language_returns_404():
    r = client.patch("/languages/nope", json={"name": "X"}, headers=admin_headers())
    assert r.status_code == 404


def test_patch_language_as_regular_user_returns_403():
    create_language(admin_headers())
    create_user()
    r = client.patch("/languages/python", json={"name": "X"}, headers=auth_headers())
    assert r.status_code == 403

