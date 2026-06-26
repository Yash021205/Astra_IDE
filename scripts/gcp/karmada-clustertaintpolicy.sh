#!/usr/bin/env bash
# Proper, fully-automatic Karmada cluster failover (v1.18).
#
# Pieces (all now in place):
#   1. --enable-taint-manager (default true): evicts workloads that do NOT
#      tolerate a NoExecute taint on a cluster.
#   2. ClusterTaintPolicy: declaratively AUTO-adds a NoExecute taint when a
#      cluster's Ready condition != True (this is what was missing — init only
#      adds NoSchedule automatically).
#   3. PropagationPolicy clusterTolerations with tolerationSeconds=30: the
#      binding tolerates the taint for 30s, then the taint-manager evicts and
#      the scheduler reschedules onto the healthy cluster.
#
# Earlier test bug: re-applying the taint in a loop reset its timeAdded, so the
# 30s toleration never elapsed. Here the taint is added ONCE by the policy.
set -uo pipefail
HC=kind-karmada-host
KCFG=$HOME/karmada-apiserver.config
K() { kubectl --kubeconfig "$KCFG" "$@"; }

echo "===== ensure member-a is back + both clusters Ready ====="
docker start member-a-control-plane >/dev/null 2>&1 || true
sleep 12
if ! K get cluster member-a >/dev/null 2>&1; then
  ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' member-a-control-plane)
  kind get kubeconfig --name member-a > /tmp/member-a.config 2>/dev/null
  kubectl --kubeconfig /tmp/member-a.config config set-cluster kind-member-a \
    --server="https://${ip}:6443" --insecure-skip-tls-verify=true >/dev/null
  karmadactl join member-a --kubeconfig "$KCFG" \
    --cluster-kubeconfig=/tmp/member-a.config --cluster-context=kind-member-a 2>&1 | tail -1
fi
for i in $(seq 1 25); do
  a=$(K get cluster member-a -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  b=$(K get cluster member-b -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  echo "  member-a=$a member-b=$b"; [ "$a" = "True" ] && [ "$b" = "True" ] && break; sleep 6
done

echo "===== (re)apply Deployment + PropagationPolicy (Divided, NoExecute tolerations) ====="
K create namespace astra-ide >/dev/null 2>&1 || true
cat <<EOF | K apply -f - | tail -2
apiVersion: apps/v1
kind: Deployment
metadata: {name: astra-ws, namespace: astra-ide, labels: {app: astra-workspace}}
spec:
  replicas: 4
  selector: {matchLabels: {app: astra-workspace}}
  template:
    metadata: {labels: {app: astra-workspace}}
    spec:
      containers: [{name: app, image: registry.k8s.io/pause:3.9}]
---
apiVersion: policy.karmada.io/v1alpha1
kind: PropagationPolicy
metadata: {name: ws-failover, namespace: astra-ide}
spec:
  propagateDeps: true
  resourceSelectors:
  - {apiVersion: apps/v1, kind: Deployment, name: astra-ws}
  placement:
    clusterAffinity: {clusterNames: [member-a, member-b]}
    clusterTolerations:
    - {key: cluster.karmada.io/not-ready,   operator: Exists, effect: NoExecute, tolerationSeconds: 30}
    - {key: cluster.karmada.io/unreachable, operator: Exists, effect: NoExecute, tolerationSeconds: 30}
    replicaScheduling:
      replicaSchedulingType: Divided
      replicaDivisionPreference: Weighted
EOF

echo "===== apply ClusterTaintPolicy: auto NoExecute when Ready != True ====="
cat <<EOF | K apply -f - | tail -1
apiVersion: policy.karmada.io/v1alpha1
kind: ClusterTaintPolicy
metadata: {name: not-ready-noexecute}
spec:
  targetClusters:
    clusterNames: [member-a, member-b]
  addOnConditions:
  - conditionType: Ready
    operator: NotIn
    statusValues: ["True"]
  removeOnConditions:
  - conditionType: Ready
    operator: In
    statusValues: ["True"]
  taints:
  - key: cluster.karmada.io/not-ready
    effect: NoExecute
EOF

for i in $(seq 1 20); do
  spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)
  echo "  spread=$spread"
  echo "$spread" | grep -q member-a && echo "$spread" | grep -q member-b && break
  sleep 6
done
echo "rb tolerations: $(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.placement.clusterTolerations}' 2>/dev/null)"

echo "===== FAIL member-a (docker stop). Taint is added AUTOMATICALLY; do NOT touch it ====="
docker stop member-a-control-plane >/dev/null
killed=$(date +%s)
for i in $(seq 1 30); do
  sleep 10
  taint=$(K get cluster member-a -o jsonpath='{.spec.taints[*].effect}' 2>/dev/null)
  ready=$(K get cluster member-a -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)
  bpods=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  echo "  +$(( $(date +%s) - killed ))s ready=$ready taint=[$taint] member-b_pods=$bpods spread=$spread"
  echo "$spread" | grep -q '"member-b","replicas":4' && { echo "RESCHEDULED_OK (automatic taint eviction)"; break; }
  echo "$spread" | grep -vq member-a && { echo "member-a evicted from binding"; }
done
echo "FINAL spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)"
echo "member-b pods=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)"
echo "CTP_DONE"
