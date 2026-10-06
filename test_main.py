from fastapi.testclient import TestClient
from main import app
import pytest
from main import get_current_user



def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["model_loaded"] is True


def test_predict_valid_input(signed_in):
    with TestClient(app) as client:
        response = client.post("/predict", json={"text": "I need a copy of my transcript"})
        assert response.status_code == 200
        data = response.json()
        assert "category" in data
        assert "confidence" in data
        assert 0 <= data["confidence"] <= 1


def test_predict_rejects_empty_input(signed_in):
    with TestClient(app) as client:
        response = client.post("/predict", json={"text": ""})
        assert response.status_code == 422


def test_predict_rejects_missing_input(signed_in):
    with TestClient(app) as client:
        response = client.post("/predict", json={})
        assert response.status_code == 422


def test_update_data_records_correction(signed_in):
    with TestClient(app) as client:
        response = client.post(
            "/update-data",
            json={"text": "test phrase for correction", "correct_category": "Advising"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Recorded"


def test_update_data_rejects_empty_text(signed_in):
    with TestClient(app) as client:
        response = client.post(
            "/update-data",
            json={"text": "", "correct_category": "Advising"}
        )
        assert response.status_code == 422


def test_update_data_rejects_missing_category(signed_in):
    with TestClient(app) as client:
        response = client.post(
            "/update-data",
            json={"text": "some phrase"}
        )
        assert response.status_code == 422


def test_update_data_requires_login():
    with TestClient(app) as client:
        response = client.post(
            "/update-data",
            json={"text": "test phrase", "correct_category": "Advising"}
        )
        assert response.status_code == 401


def test_retrain_requires_login():
    with TestClient(app) as client:
        response = client.post("/retrain")
        assert response.status_code == 401


@pytest.fixture
def signed_in():
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "username": "test-staff", "role": "staff"}
    yield
    app.dependency_overrides.clear()


def test_predict_requires_login():
    with TestClient(app) as client:
        response = client.post("/predict", json={"text": "I need my transcript"})
        assert response.status_code == 401


def test_ask_requires_login():
    with TestClient(app) as client:
        response = client.post("/ask", json={"question": "When does spring recess start?"})
        assert response.status_code == 401


def test_admin_endpoint_requires_login():
    with TestClient(app) as client:
        response = client.get("/admin/pending-corrections")
        assert response.status_code == 401


def test_staff_cannot_retrain(signed_in):
    with TestClient(app) as client:
        assert client.post("/retrain").status_code == 403


def test_staff_cannot_list_pending_corrections(signed_in):
    with TestClient(app) as client:
        assert client.get("/admin/pending-corrections").status_code == 403


def test_root_redirects_to_login_when_signed_out():
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/login")


def test_login_page_renders_when_signed_out():
    with TestClient(app) as client:
        response = client.get("/login")
        assert response.status_code == 200
