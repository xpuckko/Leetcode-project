from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool

import user
import test_case as test_case_module
from test_case import MAX_TEST_CASE_LENGTH
from database import get_session
from main import app

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@event.listens_for(test_engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

def override_get_session():
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


def create_problem(headers, title="Two Sum", is_visible=True):
    r = client.post("/problems/", json={
        "title": title,
        "description": "Add two numbers",
        "time_limit_sec": 1.0,
        "memory_limit_kb": 262144,
        "is_visible": is_visible,
        "difficulty": "easy",
    }, headers=headers)
    assert r.status_code == 201
    return r.json()


def create_test_case(headers, problem_id, input="1 2", expected_output="3", is_visible=True):
    return client.post(f"/problems/{problem_id}/test-cases/", json={
        "input": input,
        "expected_output": expected_output,
        "is_visible": is_visible,
    }, headers=headers)


def test_create_test_case_as_admin():
    h = admin_headers()
    problem = create_problem(h)
    r = create_test_case(h, problem["id"])
    assert r.status_code == 201
    data = r.json()
    assert data["input"] == "1 2"
    assert data["expected_output"] == "3"
    assert data["is_visible"] is True
    assert data["problem_id"] == problem["id"]
    assert "id" in data


def test_create_test_case_is_hidden_by_default():
    h = admin_headers()
    problem = create_problem(h)
    r = client.post(f"/problems/{problem['id']}/test-cases/", json={
        "input": "1 2",
        "expected_output": "3",
    }, headers=h)
    assert r.status_code == 201
    assert r.json()["is_visible"] is False


def test_create_test_case_as_regular_user_returns_403():
    problem = create_problem(admin_headers())
    create_user()
    r = create_test_case(auth_headers(), problem["id"])
    assert r.status_code == 403


def test_create_test_case_without_login_is_rejected():
    problem = create_problem(admin_headers())
    r = client.post(f"/problems/{problem['id']}/test-cases/", json={
        "input": "1 2",
        "expected_output": "3",
    })
    assert r.status_code in (401, 403)


def test_create_test_case_for_missing_problem_returns_404():
    r = create_test_case(admin_headers(), uuid4())
    assert r.status_code == 404


def test_create_test_case_missing_fields_returns_422():
    h = admin_headers()
    problem = create_problem(h)
    r = client.post(f"/problems/{problem['id']}/test-cases/", json={"input": "1 2"}, headers=h)
    assert r.status_code == 422


def test_create_test_case_too_long_returns_422():
    h = admin_headers()
    problem = create_problem(h)
    r = create_test_case(h, problem["id"], input="a" * (MAX_TEST_CASE_LENGTH + 1))
    assert r.status_code == 422


def test_list_test_cases_hides_hidden_ones_and_internal_fields():
    h = admin_headers()
    problem = create_problem(h)
    create_test_case(h, problem["id"], input="1 2", expected_output="3", is_visible=True)
    create_test_case(h, problem["id"], input="secret", expected_output="secret", is_visible=False)
    create_user()
    r = client.get(f"/problems/{problem['id']}/test-cases/", headers=auth_headers())
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["input"] == "1 2"
    assert set(data[0].keys()) == {"id", "input", "expected_output"}


def test_list_test_cases_without_login_is_rejected():
    problem = create_problem(admin_headers())
    r = client.get(f"/problems/{problem['id']}/test-cases/")
    assert r.status_code in 401


def test_list_test_cases_of_hidden_problem_returns_404_for_user():
    h = admin_headers()
    problem = create_problem(h, is_visible=False)
    create_test_case(h, problem["id"])
    create_user()
    r = client.get(f"/problems/{problem['id']}/test-cases/", headers=auth_headers())
    assert r.status_code == 404


def test_list_test_cases_of_hidden_problem_works_for_admin():
    h = admin_headers()
    problem = create_problem(h, is_visible=False)
    create_test_case(h, problem["id"])
    r = client.get(f"/problems/{problem['id']}/test-cases/", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_admin_list_includes_hidden_test_cases():
    h = admin_headers()
    problem = create_problem(h)
    create_test_case(h, problem["id"], is_visible=True)
    create_test_case(h, problem["id"], is_visible=False)
    r = client.get(f"/admin/problems/{problem['id']}/test-cases/", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_admin_list_as_regular_user_returns_403():
    problem = create_problem(admin_headers())
    create_user()
    r = client.get(f"/admin/problems/{problem['id']}/test-cases/", headers=auth_headers())
    assert r.status_code == 403


def test_admin_list_for_missing_problem_returns_404():
    r = client.get(f"/admin/problems/{uuid4()}/test-cases/", headers=admin_headers())
    assert r.status_code == 404


def test_get_test_case_as_admin():
    h = admin_headers()
    problem = create_problem(h)
    created = create_test_case(h, problem["id"], is_visible=False).json()
    r = client.get(f"/problems/{problem['id']}/test-cases/{created['id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_test_case_as_regular_user_returns_403():
    h = admin_headers()
    problem = create_problem(h)
    created = create_test_case(h, problem["id"]).json()
    create_user()
    r = client.get(f"/problems/{problem['id']}/test-cases/{created['id']}", headers=auth_headers())
    assert r.status_code == 403


def test_get_test_case_under_wrong_problem_returns_404():
    h = admin_headers()
    problem = create_problem(h)
    other = create_problem(h, title="Other")
    created = create_test_case(h, problem["id"]).json()
    r = client.get(f"/problems/{other['id']}/test-cases/{created['id']}", headers=h)
    assert r.status_code == 404


def test_patch_test_case_changes_only_sent_fields():
    h = admin_headers()
    problem = create_problem(h)
    created = create_test_case(h, problem["id"], input="1 2", expected_output="3", is_visible=True).json()
    r = client.patch(
        f"/problems/{problem['id']}/test-cases/{created['id']}",
        json={"expected_output": "99"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["expected_output"] == "99"
    assert r.json()["input"] == "1 2"
    assert r.json()["is_visible"] is True


def test_patch_test_case_can_hide_it():
    h = admin_headers()
    problem = create_problem(h)
    created = create_test_case(h, problem["id"], is_visible=True).json()
    r = client.patch(
        f"/problems/{problem['id']}/test-cases/{created['id']}",
        json={"is_visible": False},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["is_visible"] is False


def test_patch_test_case_as_regular_user_returns_403():
    h = admin_headers()
    problem = create_problem(h)
    created = create_test_case(h, problem["id"]).json()
    create_user()
    r = client.patch(
        f"/problems/{problem['id']}/test-cases/{created['id']}",
        json={"input": "x"},
        headers=auth_headers(),
    )
    assert r.status_code == 403


def test_patch_missing_test_case_returns_404():
    h = admin_headers()
    problem = create_problem(h)
    r = client.patch(f"/problems/{problem['id']}/test-cases/{uuid4()}", json={"input": "x"}, headers=h)
    assert r.status_code == 404


def test_delete_test_case_as_admin():
    h = admin_headers()
    problem = create_problem(h)
    created = create_test_case(h, problem["id"]).json()
    url = f"/problems/{problem['id']}/test-cases/{created['id']}"
    assert client.delete(url, headers=h).status_code == 204
    assert client.get(url, headers=h).status_code == 404


def test_delete_test_case_as_regular_user_returns_403():
    h = admin_headers()
    problem = create_problem(h)
    created = create_test_case(h, problem["id"]).json()
    create_user()
    r = client.delete(f"/problems/{problem['id']}/test-cases/{created['id']}", headers=auth_headers())
    assert r.status_code == 403


def test_deleting_a_problem_deletes_its_test_cases():
    h = admin_headers()
    problem = create_problem(h)
    create_test_case(h, problem["id"], is_visible=True)
    create_test_case(h, problem["id"], is_visible=False)

    assert client.delete(f"/problems/{problem['id']}", headers=h).status_code == 204

    with Session(test_engine) as session:
        assert session.exec(select(test_case_module.TestCase)).all() == []