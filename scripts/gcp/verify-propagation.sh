#!/usr/bin/env bash
KCFG=/etc/karmada/karmada-apiserver.config
echo "=== restart member1 (was stopped in edge-case 2) ==="
docker start member1-control-plane >/dev/null 2>&1; sleep 8
echo "=== wait for all members Ready (up to 90s) ==="
for t in $(seq 1 18); do
  ready=$(kubectl --kubeconfig "$KCFG" get clusters --no-headers 2>/dev/null | grep -c ' True ')
  echo "  members Ready: $ready/5"
  [ "$ready" = "5" ] && break
  sleep 5
done
kubectl --kubeconfig "$KCFG" get clusters
echo "=== scale workspace to 12 replicas (force spread) ==="
kubectl --kubeconfig "$KCFG" -n astra-ide scale deployment astra-workspace --replicas=12
sleep 35
echo "=== Karmada resourcebinding (propagation record) ==="
kubectl --kubeconfig "$KCFG" -n astra-ide get resourcebinding 2>/dev/null | head
echo "=== EDGE CASE 1 — pods per member (should sum to ~12 across all 5) ==="
tot=0
for i in 1 2 3 4 5; do
  p=$(kubectl --context "kind-member$i" -n astra-ide get pods --no-headers 2>/dev/null | grep -c Running)
  printf "  member%s Running pods: %s\n" "$i" "$p"; tot=$((tot+p))
done
echo "  TOTAL running across federation: $tot"
echo "VERIFY_DONE"
