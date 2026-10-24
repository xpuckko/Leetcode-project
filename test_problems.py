from fastapi.testclient import TestClient
from problems import app

client = TestClient(app)

def test_create_and_get_problem():
    payload = {
        "title": "Two Sum",
        "description": "Find two numbers that add up to target",
        "slug": "two-sum",
        "time_limit_sec": 1.0,
        "memory_limit_kb": 65536,
        "difficulty": "easy",
    }
    response = client.post("/problems/", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] is not None

    response = client.get(f"/problems/{created['id']}")
    assert response.status_code == 200
    assert response.json()["slug"] == "two-sum"

def test_get_missing_problem_returns_404():
    response = client.get("/problems/9999")
    assert response.status_code == 404