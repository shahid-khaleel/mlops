# Kubeflow Dashboard selection

This `kustomization.yaml` is **not standalone** — it's a curated list of components
(Istio, Dex, oauth2-proxy, Kubeflow namespace/roles, the Central Dashboard, and a
user Profile) picked out of the much larger
[kubeflow/community-distribution](https://github.com/kubeflow/community-distribution)
repo, at `release-26.03.1`. It deliberately excludes that repo's Notebooks, Katib,
Pipelines, Spark, and duplicate KServe/Trainer components, since this project
installs KServe and Kubeflow Trainer separately via Helm (see `../kserve/` and
`../kubeflow-trainer/`).

## How to render and apply it

```bash
git clone --depth 1 --branch release-26.03.1 \
  https://github.com/kubeflow/community-distribution.git .kubeflow-dist

# drop this file into a sibling directory inside that clone, so its
# relative "../common/..." paths resolve correctly
mkdir .kubeflow-dist/example-minimal
cp kustomization.yaml .kubeflow-dist/example-minimal/kustomization.yaml
cd .kubeflow-dist/example-minimal

kubectl kustomize . > render.yaml
for i in 1 2 3 4 5; do
  kubectl apply --server-side --force-conflicts -f render.yaml && break
  sleep 15   # CRDs/webhooks race on the first pass
done

# then apply the KServe RBAC aggregation fix so kubeflow-edit isn't empty:
kubectl apply -f ../../k8s/kserve/rbac-aggregation.yaml
```

Full context — why each excluded piece was excluded, the real resource cost
(~0.8 CPU / 2.35 GiB for this exact selection), and the login/RBAC/namespace
gotchas hit while wiring this up — is in
[`docs/churn-stack-manual.html`](../../docs/churn-stack-manual.html), §5 and §10.
