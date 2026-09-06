# MLflow

MLflow runs as a plain local process here, not as a Kubernetes workload — deliberately.
It needs no Deployment/Service YAML, so this folder just holds the exact commands used.

## Start the tracking server

```bash
pip install mlflow

python -m mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlruns \
  --host 127.0.0.1 --port 5000
```

- **Backend store** (`mlflow.db`, SQLite) — searchable run metadata: params, metrics, run status. A database backend is required for the Model Registry to work; a plain file store can't support it.
- **Artifact store** (`./mlruns`) — the actual model files each run produces.

## Train, track, and register a version

```bash
PYTHONIOENCODING=utf-8 python train.py
```

`train.py` wraps training in `mlflow.start_run()`, logs `n_estimators`/`max_depth`
and `accuracy`/`precision`/`recall`/`f1_score`, and calls
`mlflow.sklearn.log_model(model, "model", registered_model_name="churn-model")` —
that one call both logs the artifact to the run and creates the next
`churn-model` Registry version.

`PYTHONIOENCODING=utf-8` matters on Windows — without it, MLflow's success
message (which contains an emoji) crashes the default console encoding after
the run has already logged, leaving it stuck at status `RUNNING`.

## Export a version for KServe

MLflow 3.x saves scikit-learn models as `model.skops`, not the `.joblib` file
KServe's built-in sklearn server expects — `export_for_kserve.py` (repo root)
bridges that:

```bash
python export_for_kserve.py <version-number>   # -> kserve-model/model.joblib
```

See [`docs/churn-stack-manual.html`](../docs/churn-stack-manual.html) §5 and
§10 for the full API surface used and every format/version gotcha hit.
