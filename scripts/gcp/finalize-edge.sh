#!/usr/bin/env bash
KCFG=/etc/karmada/karmada-apiserver.config
N="${N:-5}"

echo "=== apply EQUAL static weights so replicas divide evenly across all $N ==="
WEIGHTS=""
for i in $(seq 1 "$N"); do
  WEIGHTS="$WEIGHTS        - targetCluster: {clusterNames: [member$i]}
          weight: 1
"
done
cat <<EOF | kubectl --kubeconfig "$KCFG" apply -f -
apiVersion: policy.karmada.io/v1alpha1
kind: PropagationPolicy
metadata: {name: ws-scale, namespace: astra-ide}
spec:
  resourceSelectors: [{apiVersion: apps/v1, kind: Deployment, labelSelector: {matchLabels: {app: astra-workspace}}}]
  placement:
    clusterAffinity: {clusterNames: [$(seq 1 $N | sed 's/^/member/' | paste -sd, -)]}
    replicaScheduling:
      replicaSchedulingType: Divided
      replicaDivisionPreference: Weighted
      weightPreference:
        staticClusterWeight:
$WEIGHTS
EOF

kubectl --kubeconfig "$KCFG" -n astra-ide scale deployment astra-workspace --replicas=15
echo "   waiting 45s for even division..."; sleep 45
echo "=== EDGE CASE 1 — even spread (each ~3 of 15) ==="
tot=0
for i in $(seq 1 "$N"); do
  p=$(kubectl --context "kind-member$i" -n astra-ide get pods --no-headers 2>/dev/null | grep -c Running)
  printf "  member%s: %s\n" "$i" "$p"; tot=$((tot+p))
done
echo "  TOTAL: $tot"

echo "=== EDGE CASE 2 — kill member3, watch Karmada migrate its share ==="
docker stop member3-control-plane >/dev/null
echo "   waiting 70s for failover (tolerationSeconds=20 + reschedule)..."; sleep 70
echo "=== pods per surviving member AFTER member3 down (member3's share moved) ==="
tot=0
for i in $(seq 1 "$N"); do
  st=$( [ "$i" = "3" ] && echo "(killed)" || echo "" )
  p=$(kubectl --context "kind-member$i" -n astra-ide get pods --no-headers 2>/dev/null | grep -c Running)
  printf "  member%s: %s %s\n" "$i" "$p" "$st"; tot=$((tot+p))
done
echo "  TOTAL on survivors: $tot"
echo "=== Karmada cluster health after failure ==="
kubectl --kubeconfig "$KCFG" get clusters
echo "FINALIZE_DONE"
