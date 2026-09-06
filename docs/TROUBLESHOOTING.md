# Troubleshooting

Seven real failures hit while building this stack, in the order encountered.
Each was diagnosed from actual error output, not assumption.

## 1. Windows console can't print MLflow's emoji

**Symptom**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f3c3'
```

**Cause** MLflow prints a 🏃 emoji on run completion. Windows' default `cp1252`
console encoding can't render it, crashing *after* the run's data was already
logged — so training succeeds, only the final status update fails.

**Fix**
```bash
PYTHONIOENCODING=utf-8 python train.py
```
If a run is already stuck at status `RUNNING`, patch it manually:
```bash
curl -X POST http://127.0.0.1:5000/api/2.0/mlflow/runs/update \
  -H "Content-Type: application/json" \
  -d '{"run_id":"<run_id>","status":"FINISHED"}'
```

---

## 2. MLflow 3.x saves sklearn models as `.skops`, not `.joblib`

**Symptom** KServe's built-in sklearn server only reads `model.joblib`; a
`model.skops` file in the same directory does nothing for it.

**Cause** MLflow's sklearn flavor now defaults to the `skops` serialization
format (a newer, safer alternative to pickle), not the older `.joblib`.

**Fix** `export_for_kserve.py` loads the model with
`mlflow.sklearn.load_model()` (format-agnostic — it reads the `MLmodel` file
to know how to load it) and re-saves it with `joblib.dump()`.

---

## 3. KServe sends arrays, the pipeline expected named columns

**Symptom**
```
"Specifying the columns using strings is only supported for dataframes."
```

**Cause** The training pipeline's `ColumnTransformer` selected `contract_type`
by name (`["contract_type"]`). KServe's V1 inference protocol sends
`instances` as a bare JSON array with no column names — internally that
becomes a plain array, not a DataFrame, and a name-based column selector only
works on a DataFrame.

**Fix** Select the column by position instead:
```python
ColumnTransformer(transformers=[("contract", OneHotEncoder(...), [4])], remainder="passthrough")
```
This works identically on a DataFrame (positional/`iloc`-style selection), so
the FastAPI app needed no change. It **does** require retraining, since the
fix is baked into the fitted pipeline.

---

## 4. Git Bash silently rewrote a Unix path into a Windows one

**Symptom**
```
X Exiting due to GUEST_NODE_RETRIEVE: Node C does not exist.
```

**Cause** MSYS2 (Git Bash's underlying environment) automatically rewrites
arguments that look like absolute Unix paths (`/mnt/models-store/...`) into
Windows paths (`C:\mnt\models-store\...`) before handing them to a native
Windows executable — `minikube cp`'s destination argument, meant to stay a
path *inside* the Linux VM, got mangled before `minikube` ever saw it.

**Fix**
```bash
MSYS_NO_PATHCONV=1 minikube cp kserve-model/model.joblib /mnt/models-store/churn-model/model.joblib
```

---

## 5. TrainJob field overrides silently did nothing

**Symptom** A `TrainJob`'s `spec.trainer.command` was set, but the pod ran
the runtime's own hardcoded command instead — no error, just silently ignored.

**Cause** Kubeflow Trainer only patches `TrainJob.spec.trainer.*` fields into
containers belonging to ML frameworks it explicitly recognizes (`torch`,
`mpi`, `jax`, …), declared via the runtime's `mlPolicy`. A bare custom
`ClusterTrainingRuntime` with no `mlPolicy` has no such wiring, so the
override is a no-op.

**Fix** Bake the desired command directly into the `ClusterTrainingRuntime`
template instead of relying on the override:
```yaml
containers:
  - name: node
    image: python:3.11-slim
    command: ["python3", "-c", "print('...')"]
```
Verified by inspecting the actual generated Job spec (`kubectl get job -o yaml`),
not by re-guessing.

---

## 6. `kubeflow-edit` was an empty aggregated role

**Symptom**
```
User 'user@example.com' is not authorized to list serving.kserve.io/v1beta1/inferenceservices
```

**Cause** `kubeflow-edit` is a Kubernetes *aggregated* ClusterRole — it has no
rules of its own, only whatever it inherits from other ClusterRoles carrying
a matching label (`rbac.authorization.kubeflow.org/aggregate-to-kubeflow-edit: "true"`).
Because KServe was installed via its own upstream Helm charts (not this
distro's bundled manifests), nothing ever created a ClusterRole with that
label — so `kubeflow-edit` was silently empty.

**Fix** Apply the official RBAC aggregation manifest KServe ships for exactly
this purpose:
```bash
kubectl apply -f k8s/kserve/rbac-aggregation.yaml
```

---

## 7. Dashboard's namespace picker didn't know "default" existed

**Symptom** The KServe Endpoints tile in the Kubeflow Dashboard showed no
data, even after the RBAC fix above.

**Cause** The Dashboard's namespace selector (`/api/workgroup/env-info`) only
lists namespaces owned by a Kubeflow **Profile** — it has no concept of an
arbitrary namespace a RoleBinding happens to grant access to. The real
`churn-model`/`sklearn-iris` InferenceServices lived in `default`, which
predates the Profile system and isn't Profile-owned.

**Fix** Deploy working copies of both InferenceServices directly into the
namespace the Dashboard already looks at:
```bash
kubectl apply -f k8s/kserve/churn-model-storage-profile-ns.yaml
kubectl apply -f k8s/kserve/profile-ns-inference-services.yaml
```

---

For the full narrative — diagrams, API traces, and exact commands used to
discover each of these — see [`churn-stack-manual.html`](churn-stack-manual.html) §10.
