"""Train the customer churn model."""

import logging
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

logging.basicConfig(level=logging.INFO)

DATA_PATH = Path("data/customers.csv")
MODEL_PATH = Path("models/model.pkl")

# Change these between runs to see MLflow track the difference.
N_ESTIMATORS = 100
MAX_DEPTH = None  # None = no limit (scikit-learn's default)

# Where the MLflow tracking server is running, and which experiment
# (a named group of runs) this training belongs to.
mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("churn-prediction")

# 1. Load the customer data.
data = pd.read_csv(DATA_PATH)

# 2. Separate input columns from the answer we want to predict.
X = data.drop("churn", axis=1)
y = data["churn"]

# 3. Keep 20% of the data aside for testing the trained model.
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y,
)

# The model cannot read words such as "monthly" directly.
# OneHotEncoder changes contract types into numeric columns.
# Column 4 is contract_type (age, tenure, monthly_charges, support_calls, contract_type).
# Selecting it by position (not by name) means this pipeline also works when
# KServe sends a plain array instead of a named DataFrame.
preprocessing = ColumnTransformer(
    transformers=[("contract", OneHotEncoder(handle_unknown="ignore"), [4])],
    remainder="passthrough",
)

# The pipeline runs preprocessing first, then trains the random forest.
model = Pipeline(
    steps=[
        ("preprocessing", preprocessing),
        (
            "classifier",
            RandomForestClassifier(
                n_estimators=N_ESTIMATORS, max_depth=MAX_DEPTH, random_state=42
            ),
        ),
    ]
)

# Everything inside this block is recorded as one MLflow "run".
with mlflow.start_run():
    # 4. Train the model using only the training data.
    model.fit(X_train, y_train)

    # 5. Check how accurately it predicts data it has not seen during training.
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    precision = precision_score(y_test, predictions)
    recall = recall_score(y_test, predictions)
    f1 = f1_score(y_test, predictions)
    print(f"Accuracy: {accuracy:.2f}")

    # 6. Save the complete pipeline so the API can use the same preprocessing.
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logging.info("Saved model to %s", MODEL_PATH)

    # Record the parameter we might change, the metrics we care about,
    # and the trained model itself, all tagged to this run.
    mlflow.log_param("n_estimators", N_ESTIMATORS)
    mlflow.log_param("max_depth", MAX_DEPTH)
    mlflow.log_metric("accuracy", accuracy)
    mlflow.log_metric("precision", precision)
    mlflow.log_metric("recall", recall)
    mlflow.log_metric("f1_score", f1)
    mlflow.sklearn.log_model(model, "model", registered_model_name="churn-model")
