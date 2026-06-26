#!/usr/bin/env bash
# Fix kind+Karmada Push-mode joins: members must be reachable from INSIDE the
# karmada-host cluster, so use `kind get kubeconfig --internal` (container address
# on the shared 'kind' docker network) instead of the 127.0.0.1:hostport kubeconfig.
KCFG=/etc/karmada/karmada-apiserver.config
N="${N:-5}"

echo "=== ensure all members running ==="
for i in $(seq 1 "$N"); do docker start "member$i-control-plane" >/dev/null 2>&1; done
sleep 8

echo "=== drop the broken cluster registrations ==="
for i in $(seq 1 "$N"); do kubectl --kubeconfig "$KCFG" delete cluster "member$i" 2>/dev/null; done
sleep 5

echo "=== re-join each member with its INTERNAL kubeconfig ==="
for i in $(seq 1 "$N"); do
  kind get kubeconfig --internal --name "member$i" > "/tmp/member$i-int.config" 2>/dev/null
  CTX=$(kubectl --kubeconfig "/tmp/member$i-int.config" config current-context)
  karmadactl --kubeconfig "$KCFG" join "member$i" \
    --cluster-kubeconfig="/tmp/member$i-int.config" --cluster-context="$CTX" 2>&1 | tail -1
done

echo "=== wait for members Ready (up to 120s) ==="
for t in $(seq 1 24); do
  ready=$(kubectl --kubeconfig "$KCFG" get clusters --no-headers 2>/dev/null | grep -cw True)
  echo "  Ready: $ready/$N"; [ "$ready" = "$N" ] && break; sleep 5
done
kubectl --kubeconfig "$KCFG" get clusters

echo "=== scale workspace to 12 + let Karmada divide it ==="
kubectl --kubeconfig "$KCFG" -n astra-ide scale deployment astra-workspace --replicas=12
sleep 40
kubectl --kubeconfig "$KCFG" -n astra-ide get resourcebinding 2>/dev/null | head -2

echo "=== EDGE CASE 1 — Running pods per member (should sum ~12 across $N) ==="
tot=0
for i in $(seq 1 "$N"); do
  p=$(kubectl --context "kind-member$i" -n astra-ide get pods --no-headers 2>/dev/null | grep -c Running)
  printf "  member%s: %s\n" "$i" "$p"; tot=$((tot+p))
done
echo "  TOTAL across federation: $tot"
echo "REJOIN_DONE"
