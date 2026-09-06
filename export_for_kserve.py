"""Export a registered MLflow model into the plain .joblib format that
KServe's built-in sklearn model server expects.

This does not touch train.py or retrain anything - it just loads an
already-trained model from the MLflow Model Registry and re-saves it.
"""

import sys
from pathlib import Path

import joblib
import mlflow

MODEL_NAME = "churn-model"
OUTPUT_DIR = Path("kserve-model")

if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else "2"

    mlflow.set_tracking_uri("http://127.0.0.1:5000")

    model_uri = f"models:/{MODEL_NAME}/{version}"
    print(f"Loading {model_uri} from the MLflow Model Registry...")
    model = mlflow.sklearn.load_model(model_uri)

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "model.joblib"
    joblib.dump(model, output_path)
    print(f"Saved {output_path} (ready for KServe's sklearn server)")
