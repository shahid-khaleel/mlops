# k8s/

One subfolder per technology — each is independently applicable except where noted.

| Folder | Technology | Apply with |
|---|---|---|
| [`fastapi/`](fastapi) | The original churn-prediction API | `kubectl apply -f k8s/fastapi/` |
| [`kserve/`](kserve) | Model serving (KServe, Standard/RawDeployment mode) | see below — order matters |
| [`kubeflow-trainer/`](kubeflow-trainer) | Kubeflow Trainer — a verified `TrainJob` | `kubectl apply -f k8s/kubeflow-trainer/` |
| [`kubeflow-dashboard/`](kubeflow-dashboard) | Istio + Dex + oauth2-proxy + Dashboard | see its own README — not a plain `kubectl apply` |

MLflow has no folder here — it runs as a local process, not a Kubernetes
workload. See [`../mlflow/`](../mlflow).

## `kserve/` apply order

KServe itself (CRDs, controller, serving runtimes) is installed via Helm —
see [`docs/churn-stack-manual.html`](../docs/churn-stack-manual.html) §12
Stage 2 for those exact commands. Once that's up:

```bash
# 1. the public test model
kubectl apply -f kserve/inference-service-test-model.yaml

# 2. storage bridge + the real model, in the default namespace
kubectl apply -f kserve/churn-model-storage.yaml
kubectl apply -f kserve/churn-inference-service.yaml

# 3. RBAC so the Kubeflow Dashboard's KServe Endpoints tile can read InferenceServices
#    (kubeflow-edit is an empty aggregated role until this is applied - see manual §10-06)
kubectl apply -f kserve/rbac-aggregation.yaml

# 4. only if you've also installed the Kubeflow Dashboard: duplicate the model
#    into the namespace the Dashboard actually looks at (see manual §10-07)
kubectl apply -f kserve/churn-model-storage-profile-ns.yaml
kubectl apply -f kserve/profile-ns-inference-services.yaml
```

`rbac-default-ns-access.yaml` is an earlier, superseded fix (grants RBAC on
the `default` namespace) — kept for reference; `profile-ns-inference-services.yaml`
is the approach that actually made the Dashboard show data.
