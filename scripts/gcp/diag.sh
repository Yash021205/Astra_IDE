#!/usr/bin/env bash
KCFG=/etc/karmada/karmada-apiserver.config
echo "=== member containers running? ==="
docker ps --format '{{.Names}}' | grep -E 'member|karmada-host' | sort
echo "=== internal kubeconfig server URL (member2) ==="
kind get kubeconfig --internal --name member2 2>/dev/null | grep server
echo "=== fresh join member2 (full output) ==="
kind get kubeconfig --internal --name member2 > /tmp/m2.config 2>/dev/null
CTX=$(kubectl --kubeconfig /tmp/m2.config config current-context 2>/dev/null)
echo "context=$CTX"
karmadactl --kubeconfig "$KCFG" join member2 --cluster-kubeconfig=/tmp/m2.config --cluster-context="$CTX" 2>&1 | tail -4
sleep 20
echo "=== cluster status condition (why NotReady) ==="
kubectl --kubeconfig "$KCFG" describe cluster member2 2>&1 | grep -A8 'Conditions:' | head -12
echo "=== can a karmada-host POD reach member2 API? ==="
M2IP=$(docker inspect -f '{{.NetworkSettings.Networks.kind.IPAddress}}' member2-control-plane 2>/dev/null)
echo "member2 container IP on kind net: $M2IP"
docker exec karmada-host-control-plane sh -c "getent hosts member2-control-plane; curl -sk --max-time 4 https://member2-control-plane:6443/version 2>&1 | head -3" 2>&1 | head -6
echo "DIAG_DONE"
