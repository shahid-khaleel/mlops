# Setup Guide — Deployment Runbook

The exact sequence, in the exact order, used to build this stack. Follow it
top to bottom; each step names the failure it avoids, with a link into
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the full story if you hit it anyway.

Stages 0→1→2→3 are strictly sequential. Stages 4 and 5 are independent —
skip either without breaking anything upstream.

## Prerequisites

- Docker Desktop, Minikube, kubectl, Helm installed
- Python 3.11+ and `pip`

---

## Stage 0 — Confirm the baseline

1. Deploy the existing FastAPI app and confirm it's healthy before adding anything on top.

   ```bash
   kubectl apply -f k8s/fastapi/deployment.yaml -f k8s/fastapi/service.yaml
   kubectl get pods,svc
   ```
   **Expect:** `churn-api` pod `1/1 Running`.

2. Set real node resources *before* installing anything heavy — every later
   stage's "does it fit" math depends on this number.

   ```bash
   minikube start --cpus=4 --memory=13900mb   # Docker Desktop caps memory below 14000mb
   docker inspect minikube --format 'CPU={{.HostConfig.NanoCpus}} Mem={{.HostConfig.Memory}}'
   ```
   Trust this `docker inspect` number, not `kubectl describe node` — the
   latter can cache a stale figure after a resize.

---

## Stage 1 — MLflow tracking + registry

*Local process, no cluster changes. See [`../mlflow/README.md`](../mlflow/README.md) for the full API surface.*

1. Install MLflow and start the tracking server **with a database backend from
   the start** — a plain file store can't be upgraded to support the Model
   Registry later without redoing this step.

   ```bash
   pip install mlflow
   python -m mlflow server --backend-store-uri sqlite:///mlflow.db \
     --default-artifact-root ./mlruns --host 127.0.0.1 --port 5000
   ```

2. `train.py` already contains the tracking calls (`set_tracking_uri`,
   `set_experiment`, `start_run`, `log_param`/`log_metric`, and
   `log_model(..., registered_model_name="churn-model")` — that one kwarg is
   what makes every future run auto-version).

3. Run training with UTF-8 output forced, every time, on Windows:

   ```bash
   PYTHONIOENCODING=utf-8 python train.py
   ```
   Skipping this reproduces [TROUBLESHOOTING.md #1](TROUBLESHOOTING.md#1-windows-console-cant-print-mlflows-emoji).

4. Verify a version was actually registered:

   ```bash
   curl -s http://127.0.0.1:5000/api/2.0/mlflow/model-versions/search \
     -X POST -H "Content-Type: application/json" \
     -d '{"filter":"name=\"churn-model\""}'
   ```
   **Expect:** at least one entry under `model_versions`.

---

## Stage 2 — KServe, Standard mode (no Istio yet)

1. cert-manager first — everything else's webhooks depend on it being *ready*, not just applied.

   ```bash
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.0/cert-manager.yaml
   kubectl wait --for=condition=Ready pods --all -n cert-manager --timeout=120s
   ```

2. KServe CRDs, then the controller, explicitly in Standard mode (no Knative/Istio):

   ```bash
   helm install kserve-crd oci://ghcr.io/kserve/charts/kserve-crd \
     --version v0.20.0 --namespace kserve --create-namespace

   helm install kserve-resources oci://ghcr.io/kserve/charts/kserve-resources \
     --version v0.20.0 --namespace kserve \
     --set kserve.controller.deploymentMode=Standard --wait
   ```

3. The serving runtimes (sklearn, xgboost, …) are a **separate chart** with
   its own switch — easy to miss:

   ```bash
   helm install kserve-runtime-configs oci://ghcr.io/kserve/charts/kserve-runtime-configs \
     --version v0.20.0 --namespace kserve \
     --set kserve.servingruntime.enabled=true
   ```
   Skip this and every InferenceService fails with
   `no runtime found to support predictor with model type`.

4. Prove the install with the public test model before touching your own:

   ```bash
   kubectl apply -f k8s/kserve/inference-service-test-model.yaml
   kubectl get inferenceservice sklearn-iris
   ```
   **Expect:** `READY: True` within ~2 minutes (image pull + model download).

---

## Stage 3 — Your real model onto KServe

1. Fix the pipeline's column selection **before** exporting — in `train.py`,
   then retrain, so the fix is baked into the artifact:

   ```python
   # ColumnTransformer(..., [4])   # position, not ["contract_type"]
   ```
   ```bash
   PYTHONIOENCODING=utf-8 python train.py
   ```
   Skipping this reproduces [TROUBLESHOOTING.md #3](TROUBLESHOOTING.md#3-kserve-sends-arrays-the-pipeline-expected-named-columns).

2. Export the registered version to the format KServe's sklearn server expects:

   ```bash
   python export_for_kserve.py <version-number>   # writes kserve-model/model.joblib
   ```

3. Copy it onto the Minikube node (disable Git Bash path-mangling if on Windows):

   ```bash
   minikube ssh -- "sudo mkdir -p /mnt/models-store/churn-model"
   MSYS_NO_PATHCONV=1 minikube cp kserve-model/model.joblib \
     /mnt/models-store/churn-model/model.joblib
   ```
   Omitting `MSYS_NO_PATHCONV=1` reproduces [TROUBLESHOOTING.md #4](TROUBLESHOOTING.md#4-git-bash-silently-rewrote-a-unix-path-into-a-windows-one).

4. Create the PV/PVC bridge, then the real InferenceService, then the RBAC fix:

   ```bash
   kubectl apply -f k8s/kserve/churn-model-storage.yaml
   kubectl apply -f k8s/kserve/churn-inference-service.yaml
   kubectl apply -f k8s/kserve/rbac-aggregation.yaml
   ```
   **Expect:**
   ```bash
   curl -X POST http://<churn-model-predictor>/v1/models/churn-model:predict \
     -d '{"instances":[[35,12,70.5,2,"Month-to-month"]]}'
   # -> {"predictions":[0]}
   ```

---

## Stage 4 — Kubeflow Trainer *(optional)*

1. One Helm install, defaults off (no bundled LLM runtimes):

   ```bash
   helm install kubeflow-trainer oci://ghcr.io/kubeflow/charts/kubeflow-trainer \
     --namespace kubeflow-system --create-namespace --version 2.3.0
   ```

2. For a custom runtime (not one of the bundled torch/deepspeed images), bake
   the command directly into the `ClusterTrainingRuntime` — don't rely on
   `TrainJob.spec.trainer` overrides:

   ```bash
   kubectl apply -f k8s/kubeflow-trainer/simple-training-runtime.yaml
   kubectl apply -f k8s/kubeflow-trainer/hello-trainjob.yaml
   kubectl get trainjob hello-trainjob
   ```
   See [TROUBLESHOOTING.md #5](TROUBLESHOOTING.md#5-trainjob-field-overrides-silently-did-nothing) for why overrides don't apply here.

---

## Stage 5 — Kubeflow Dashboard (Istio + Dex + Profiles) *(optional, the most expensive stage)*

Full detail in [`k8s/kubeflow-dashboard/README.md`](../k8s/kubeflow-dashboard/README.md).

1. Confirm headroom covers ~0.8 CPU / ~2.3 GiB minimum before starting:

   ```bash
   kubectl describe node minikube | grep -A6 "Allocated resources"
   ```

2. Render and apply the trimmed Kustomize build (see that README for the exact
   clone + render commands), with retries — CRDs and webhooks race on a first pass:

   ```bash
   for i in 1 2 3 4 5; do
     kubectl apply --server-side --force-conflicts -f render.yaml && break
     sleep 15
   done
   ```

3. Apply the RBAC aggregation fix (same file as Stage 3):

   ```bash
   kubectl apply -f k8s/kserve/rbac-aggregation.yaml
   ```
   Without it: [TROUBLESHOOTING.md #6](TROUBLESHOOTING.md#6-kubeflow-edit-was-an-empty-aggregated-role).

4. Log in and confirm the identity chain:

   ```bash
   kubectl port-forward svc/istio-ingressgateway -n istio-system 8090:80
   # browser -> http://127.0.0.1:8090 -> "Sign in with Dex" -> user@example.com / 12341234
   ```
   **Expect:** page title becomes `Kubeflow Central Dashboard`.

5. Deploy any InferenceService you want the Dashboard to show **into the
   Profile namespace from the start**, not `default`:

   ```bash
   kubectl apply -f k8s/kserve/churn-model-storage-profile-ns.yaml
   kubectl apply -f k8s/kserve/profile-ns-inference-services.yaml
   ```
   Deploying into `default` first reproduces [TROUBLESHOOTING.md #7](TROUBLESHOOTING.md#7-dashboards-namespace-picker-didnt-know-default-existed).

6. Install the KServe Endpoints tile, if you want more than a shell:

   ```bash
   helm install kserve-ui <path-to-kserve-ui-chart> --namespace kserve --set kubeflow.enabled=true
   ```
   **Expect:** `/kserve-endpoints/api/namespaces/kubeflow-user-example-com/inferenceservices` returns `"success":true` with real entries.

---

For architecture diagrams, full API specs, and the complete narrative behind
every decision, see [`churn-stack-manual.html`](churn-stack-manual.html).
