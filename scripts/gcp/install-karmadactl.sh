#!/usr/bin/env bash
set -e
V=v1.18.0
echo "=== download karmadactl $V ==="
curl -fsSLo /tmp/karmadactl.tgz "https://github.com/karmada-io/karmada/releases/download/${V}/karmadactl-linux-amd64.tgz"
tar -xzf /tmp/karmadactl.tgz -C /tmp
sudo install -m0755 /tmp/karmadactl /usr/local/bin/karmadactl
echo "=== verify ==="
karmadactl version
command -v karmadactl && echo "KARMADACTL_OK"
