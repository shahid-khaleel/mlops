"""A small FastAPI service for customer churn predictions."""

import logging
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)

MODEL_PATH = Path("models/model.pkl")
model = joblib.load(MODEL_PATH)
logging.info("Model loaded from %s", MODEL_PATH)

app = FastAPI(title="Customer Churn Prediction API")


class Customer(BaseModel):
    age: int
    tenure: int
    monthly_charges: float
    support_calls: int
    contract_type: str


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/predict")
def predict(customer: Customer):
    # Put the request into a one-row DataFrame with the same column names
    # used during training.
    customer_data = pd.DataFrame(
        [
            {
                "age": customer.age,
                "tenure": customer.tenure,
                "monthly_charges": customer.monthly_charges,
                "support_calls": customer.support_calls,
                "contract_type": customer.contract_type,
            }
        ]
    )

    prediction = int(model.predict(customer_data)[0])
    probability = float(model.predict_proba(customer_data)[0][1])

    return {
        "prediction": prediction,
        "churn": bool(prediction),
        "probability": round(probability, 2),
    }
