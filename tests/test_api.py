from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_predict():
    customer = {
        "age": 35,
        "tenure": 24,
        "monthly_charges": 75.5,
        "support_calls": 3,
        "contract_type": "monthly",
    }

    response = client.post("/predict", json=customer)
    result = response.json()

    assert response.status_code == 200
    assert result["prediction"] in [0, 1]
    assert isinstance(result["churn"], bool)
    assert 0 <= result["probability"] <= 1
