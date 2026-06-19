# Deployment Guide

Three deployment modes, all at $0 cost.

---

## Mode 1: Local dev with Docker Compose

Fastest path. No Kubernetes required.

```bash
cd deploy
docker compose -f docker-compose.yml up --build
```

Then:
- Frontend: http://localhost:3000
- Backend:  http://localhost:8000
- API docs: http://localhost:8000/api/v1/docs
- Collab:   ws://localhost:1234
- MinIO console: http://localhost:9001  (admin / admin12345)

Stop with `docker compose down`. Volumes are preserved unless you add `-v`.

---

## Mode 2: Local dev WITHOUT containers (fast iteration)

Run data plane in Docker, app code natively:

```bash
# Terminal 1 — data plane
docker compose -f deploy/docker-compose.dev.yml up -d

# Terminal 2 — backend (hot reload)
cd backend
python -m venv venv && source venv/bin/activate   # (Windows: venv\Scripts\activate)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 3 — frontend (hot reload)
cd frontend
npm install
npm run dev
```

---

## Mode 3: Production-like on Kubernetes

### 3.1  Single-node k3s — choose your free provider

**Recommended: Azure for Students** ($100 + 750 hr/mo B1s VM, no credit card)

1. Sign in at https://portal.azure.com (Student account already provisioned).
2. Create a VM:
   - Image: Ubuntu Server 24.04 LTS
   - Size: **B2s** (2 vCPU, 4 GB RAM) — covered by the $100 credit
     - Or **B1s** for free-tier-only (1 vCPU, 1 GB — k3s tight but works for demo)
   - Authentication: SSH public key
   - Inbound ports: SSH (22), HTTP (80), HTTPS (443), 30000-32767 (NodePort range)
3. SSH in:
   ```bash
   ssh azureuser@<VM_PUBLIC_IP>
   ```
4. Install k3s:
   ```bash
   curl -sfL https://get.k3s.io | sh -
   sudo cat /etc/rancher/k3s/k3s.yaml   # copy kubeconfig
   ```
5. Build & push images (CI does this automatically on push to main):
   ```bash
   docker build -t ghcr.io/prasannamishra001/astra-ide-backend:latest backend
   docker push ghcr.io/prasannamishra001/astra-ide-backend:latest
   # Repeat for frontend, collab-server
   ```
6. Apply manifests:
   ```bash
   kubectl apply -k k8s/base
   ```
7. Install supporting charts:
   ```bash
   helm repo add bitnami https://charts.bitnami.com/bitnami
   helm install postgres bitnami/postgresql -n astra-ide
   helm install redis    bitnami/redis      -n astra-ide
   helm install minio    bitnami/minio      -n astra-ide
   ```

**Alternative: Oracle Cloud Always-Free**
Free ARM Ampere A1 VM (4 OCPU, 24 GB RAM) forever — but **requires credit card for identity verification**. If your card is declined or you can't add one, use Azure instead.

**Alternative: AWS Educate**
$35 credit (or $100 if your college is a member). Sign up at aws.amazon.com/education/awseducate.

**Alternative: GCP Free Trial**
$300 credit for 90 days. After expiry, the always-free e2-micro VM (1 vCPU, 1 GB) is enough for a single-node k3s demo.

### 3.2  Multi-cluster with Karmada

After two clusters are running:

```bash
helm repo add karmada-charts https://raw.githubusercontent.com/karmada-io/karmada/master/charts
helm install karmada karmada-charts/karmada -n karmada-system --create-namespace

# Join each cluster
karmadactl join cluster-a --cluster-kubeconfig=cluster-a.kubeconfig
karmadactl join cluster-b --cluster-kubeconfig=cluster-b.kubeconfig

# Apply propagation policy
kubectl apply -f k8s/karmada/propagation-policy.yaml
```

### 3.3  Sandbox runtimes

On each worker node:

```bash
# gVisor (runsc)
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | sudo tee /etc/apt/sources.list.d/gvisor.list > /dev/null
sudo apt-get update && sudo apt-get install -y runsc

# Kata Containers (Firecracker backend)
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/kata-containers/kata-containers/main/utils/kata-manager.sh) install-packages-from-tag"

# Label the nodes
kubectl label node <node> sandbox.astra-ide.io/gvisor=true
kubectl label node <node> sandbox.astra-ide.io/firecracker=true

# Apply the runtime classes
kubectl apply -f k8s/base/runtime-classes.yaml
```

### 3.4  Observability stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace

helm repo add cilium https://helm.cilium.io
helm install tetragon cilium/tetragon -n kube-system
kubectl apply -f k8s/base/eBPF-tetragon-policy.yaml
```

### 3.5  KEDA autoscaling

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda -n keda-system --create-namespace

kubectl apply -f k8s/base/keda-scaledobject.yaml
```

---

## Free resources used

| Service | Provider | Free tier |
|---|---|---|
| Compute (primary)  | Azure for Students   | $100 credit + 750 hr/mo B1s VM (no card) |
| Compute (alt)      | Oracle Cloud Always-Free | 4 OCPU + 24GB ARM, forever (card required) |
| Compute (alt)      | GCP Free               | 1 e2-micro VM, always-free |
| Container registry | GitHub GHCR            | Unlimited public, 500 MB private |
| CI                 | GitHub Actions         | 2000 min/mo private, ∞ public |
| TLS certificates   | cert-manager + Let's Encrypt | Free |
| DNS                | Cloudflare             | Free |
| Carbon API         | electricityMaps free   | 1000 req/mo, all zones |
| Carbon API (alt)   | UK Carbon Intensity    | No key, UK only |
| Carbon API (alt)   | WattTime               | Free for academic research |

**Total monthly cost: $0**

## API keys setup

### electricityMaps

1. Free signup at https://www.electricitymaps.com/free-tier-api
2. Paste your token into `backend/.env`:
   ```
   ELECTRICITY_MAPS_TOKEN=your_token_here
   ELECTRICITY_MAPS_ZONE=DK-DK1   # or IN-NO for India, etc.
   ```
3. The backend exposes `/api/v1/carbon/intensity?zone=...` for read access, and the PPO scheduler consumes the normalized value via `CarbonService.get_normalized()`.
4. If the API is unreachable or the quota is hit, the service falls back to a built-in zone-average table (`_FALLBACK_BY_ZONE` in `carbon_service.py`) — training never breaks.

**Never commit your `.env`** — it's gitignored. For CI, store the token as a GitHub Actions secret named `ELECTRICITY_MAPS_TOKEN`.
