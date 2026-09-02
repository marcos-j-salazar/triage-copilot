from fastapi.testclient import TestClient
from main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["model_loaded"] is True


def test_predict_valid_input():
    with TestClient(app) as client:
        response = client.post("/predict", json={"text": "I need a copy of my transcript"})
        assert response.status_code == 200
        data = response.json()
        assert "category" in data
        assert "confidence" in data
        assert 0 <= data["confidence"] <= 1


def test_predict_rejects_empty_input():
    with TestClient(app) as client:
        response = client.post("/predict", json={"text": ""})
        assert response.status_code == 422


def test_predict_rejects_missing_input():
    with TestClient(app) as client:
        response = client.post("/predict", json={})
        assert response.status_code == 422

def test_update_data_records_correction():
    with TestClient(app) as client:
        response = client.post("/update-data", json={
            "text": "test phrase for correction",
            "correct_category": "Advising"
        })
        assert response.status_code == 200
        assert response.json()["status"] == "Recorded"

def test_update_data_rejects_empty_text():
    with TestClient(app) as client:
        response = client.post("/update-data", json={
            "text": "",
            "correct_category": "Advising"
        })
        assert response.status_code == 422

def test_update_data_rejects_missing_category():
    with TestClient(app) as client:
        response = client.post("/update-data", json={
            "text": "some phrase"
        })
        assert response.status_code == 422
