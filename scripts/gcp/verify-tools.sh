#!/usr/bin/env bash
set -e
if ! command -v helm >/dev/null; then
  echo "=== install helm (binary) ==="
  curl -fsSLo /tmp/helm.tgz https://get.helm.sh/helm-v3.16.4-linux-amd64.tar.gz
  tar -xzf /tmp/helm.tgz -C /tmp
  sudo install -m0755 /tmp/linux-amd64/helm /usr/local/bin/helm
fi
echo "=== rootfs (should be ~60G now) ==="
df -h / | sed -n '2p'
echo "=== versions ==="
echo -n "kind       "; kind version
echo -n "kubectl    "; kubectl version --client 2>/dev/null | head -1
echo -n "karmadactl "; karmadactl version 2>/dev/null | head -1
echo -n "helm       "; helm version --short 2>/dev/null
echo -n "docker     "; docker version --format '{{.Server.Version}}' 2>/dev/null || echo "(server n/a)"
echo "TOOLS_READY"
