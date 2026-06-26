# B5 — Karmada multi-cluster federation: setup & verify

Stands up a real 2-cluster federation with **kind** (Kubernetes-in-Docker) +
**Karmada**, registers the clusters, and propagates an ASTRA workspace across both
— the live counterpart to the `ml/federation` simulation.

> **Needs Docker + a Linux environment.** kind/Karmada cannot run on Windows
> directly. Run this on **one of**:
> - the **GCP Linux VM** (`34.47.224.18`) — recommended, the guide-approved box; or
> - **Docker Desktop + WSL2** on the Windows machine; or
> - the **college GPU/Linux PC**.
> Everything below is one-time (~10 min). The simulation + tests
> (`ml/federation`) run anywhere without this.

## 0. Prereqs (on the Linux host)
```bash
# Docker (already on the VM), kubectl, kind, and the Karmada CLI:
[ -x "$(command -v kind)" ] || go install sigs.k8s.io/kind@latest
curl -fsSL https://raw.githubusercontent.com/karmada-io/karmada/master/hack/install-cli.sh | sudo bash
curl -fsSL https://raw.githubusercontent.com/karmada-io/karmada/master/hack/install-cli.sh | sudo bash -s kubectl-karmada
```

## 1. Create the host + two member clusters (kind)
```bash
kind create cluster --name karmada-host
kind create cluster --name cluster-a       # low-carbon (e.g. Denmark)
kind create cluster --name cluster-b       # e.g. India
```

## 2. Install the Karmada control plane on the host cluster
```bash
kubectl config use-context kind-karmada-host
kubectl karmada init --kubeconfig=$HOME/.kube/config
export KARMADA="$HOME/.kube/karmada-apiserver.config"   # written by `init`
```

## 3. Register the two member clusters
```bash
kubectl karmada --kubeconfig $KARMADA join cluster-a \
  --cluster-kubeconfig=$HOME/.kube/config --cluster-context=kind-cluster-a
kubectl karmada --kubeconfig $KARMADA join cluster-b \
  --cluster-kubeconfig=$HOME/.kube/config --cluster-context=kind-cluster-b
kubectl --kubeconfig $KARMADA get clusters        # both should be Ready
```

## 4. Apply the federation policy + a workspace
```bash
kubectl --kubeconfig $KARMADA create namespace astra-ide
kubectl --kubeconfig $KARMADA apply -f k8s/karmada/workspace-propagation.yaml
# a sample workspace pod (label app=astra-workspace is what the policy selects):
kubectl --kubeconfig $KARMADA apply -f k8s/base/workspace-template.yaml   # fill placeholders first
```

## 5. Verify cross-cluster propagation (the proof)
```bash
# Karmada shows the resource spread across members:
kubectl --kubeconfig $KARMADA get resourcebinding -n astra-ide
# and the pod actually exists on each member cluster:
kubectl --context kind-cluster-a get pods -n astra-ide
kubectl --context kind-cluster-b get pods -n astra-ide
```
You should see the workspace scheduled across **cluster-a** and **cluster-b** per
the 70/30 weight — that is the federation working. Migration: cordon/drain
cluster-a and watch Karmada reschedule onto cluster-b (the `clusterTolerations`).

## What this demonstrates for B5
- **Real cross-cluster scheduling** (not just the simulation): one API, two clusters.
- **Migration on cluster failure** (tolerations) — the report's "migrate when saturated/unhealthy".
- The AI loop (`ml/federation/optimizer.py`) is what updates the propagation
  weights at runtime; Karmada is the mechanism that enforces them.

## If you hit issues / need help
- `kind create` failing on the VM → ensure Docker is running and the user is in the
  `docker` group (`sudo usermod -aG docker $USER` then re-login).
- Low RAM on the VM → create only `karmada-host` + `cluster-a` + `cluster-b` with
  1 node each (kind default); stop other workloads. This is where the
  **guide-approved larger box / GPU PC** helps if the e2-standard-4 is tight.
