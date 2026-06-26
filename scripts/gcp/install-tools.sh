#!/usr/bin/env bash
# Bootstrap the GCP VM for the Karmada + eBPF scale test: grow the rootfs (after
# the boot disk is resized via gcloud) and install kind / kubectl / karmadactl /
# helm. Idempotent.
set -e
echo "=== grow rootfs to match resized disk ==="
sudo growpart /dev/sda 1 2>/dev/null || echo "(growpart: nothing to do)"
sudo resize2fs /dev/sda1 2>/dev/null || echo "(resize2fs: nothing to do)"
df -h / | sed -n '2p'

ARCH=amd64
install_bin() { sudo install -m 0755 "$1" "/usr/local/bin/$2"; rm -f "$1"; }

if ! command -v kind >/dev/null; then
  echo "=== install kind ==="
  curl -fsSLo kind "https://kind.sigs.k8s.io/dl/v0.31.0/kind-linux-${ARCH}"
  install_bin kind kind
fi
if ! command -v kubectl >/dev/null; then
  echo "=== install kubectl ==="
  KV=$(curl -fsSL https://dl.k8s.io/release/stable.txt)
  curl -fsSLo kubectl "https://dl.k8s.io/release/${KV}/bin/linux/${ARCH}/kubectl"
  install_bin kubectl kubectl
fi
if ! command -v karmadactl >/dev/null; then
  echo "=== install karmadactl ==="
  curl -fsSL https://raw.githubusercontent.com/karmada-io/karmada/master/hack/install-cli.sh | sudo bash
fi
if ! command -v helm >/dev/null; then
  echo "=== install helm ==="
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

echo "=== versions ==="
kind version; kubectl version --client 2>/dev/null | head -1; karmadactl version 2>/dev/null | head -1; helm version --short 2>/dev/null
echo "=== docker ok? ==="; docker ps >/dev/null 2>&1 && echo yes || echo "no (group?)"
echo "BOOTSTRAP_DONE"
