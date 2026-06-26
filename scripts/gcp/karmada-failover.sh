#!/usr/bin/env bash
# B5 — Karmada CLUSTER FAILOVER gate. Stands up a Karmada host + two member
# clusters (kind), propagates a Deployment Divided 50/50 across both, then KILLS
# member-a and shows Karmada evict + RESCHEDULE its replicas onto member-b.
#
# The "failover gate" = Karmada's Failover feature gate (default-on in recent
# releases) + NoExecute cluster tolerations with a short tolerationSeconds so
# eviction happens in ~30s instead of the 300s default.
set -uo pipefail
HOST=karmada-host; MA=member-a; MB=member-b
K() { kubectl --kubeconfig "$KCFG" "$@"; }

echo "== cleanup + raise inotify limits =="
kind delete cluster --name tetra >/dev/null 2>&1 || true
for c in $HOST $MA $MB; do kind delete cluster --name "$c" >/dev/null 2>&1 || true; done
sudo sysctl -w fs.inotify.max_user_instances=8192 >/dev/null
sudo sysctl -w fs.inotify.max_user_watches=1048576 >/dev/null

echo "== create host + 2 member clusters =="
kind create cluster --name $HOST --wait 120s
kind create cluster --name $MA   --wait 120s
kind create cluster --name $MB   --wait 120s

echo "== init Karmada control plane on host =="
kubectl config use-context kind-$HOST
sudo karmadactl init --kubeconfig "$HOME/.kube/config" >/tmp/kinit.log 2>&1 || { tail -20 /tmp/kinit.log; exit 1; }
# karmadactl writes the apiserver config root-owned under /etc/karmada (dir is
# 0700, so plain kubectl can't even traverse it). Copy to a user-owned path.
KCFG=$HOME/karmada-apiserver.config
sudo cp /etc/karmada/karmada-apiserver.config "$KCFG"
sudo chown "$(id -u):$(id -g)" "$KCFG"
chmod 600 "$KCFG"

echo "== ensure Failover + GracefulEviction feature gates on controllers =="
for d in karmada-controller-manager karmada-scheduler; do
  kubectl -n karmada-system get deploy $d >/dev/null 2>&1 && \
  kubectl -n karmada-system patch deploy $d --type=json -p \
    '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--feature-gates=Failover=true,GracefulEviction=true"}]' 2>/dev/null || true
done
kubectl -n karmada-system rollout status deploy/karmada-controller-manager --timeout=120s | tail -1

echo "== join members (rewrite server to container IP on shared kind network) =="
join_member() {
  local name=$1 ctx=kind-$1
  local ip; ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ${1}-control-plane)
  local cfg=/tmp/${1}.config
  kind get kubeconfig --name "$1" > "$cfg"
  kubectl --kubeconfig "$cfg" config set-cluster "$ctx" \
    --server="https://${ip}:6443" --insecure-skip-tls-verify=true >/dev/null
  sudo karmadactl --kubeconfig "$KCFG" join "$name" \
    --cluster-kubeconfig="$cfg" --cluster-context="$ctx" 2>&1 | tail -1
}
join_member $MA
join_member $MB
sleep 5
echo "clusters:"; K get clusters

echo "== apply failover PropagationPolicy + Deployment (Divided 50/50, 4 replicas) =="
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
      containers:
      - {name: app, image: registry.k8s.io/pause:3.9}
---
apiVersion: policy.karmada.io/v1alpha1
kind: PropagationPolicy
metadata: {name: ws-failover, namespace: astra-ide}
spec:
  propagateDeps: true
  resourceSelectors:
  - {apiVersion: apps/v1, kind: Deployment, name: astra-ws}
  placement:
    clusterAffinity: {clusterNames: [$MA, $MB]}
    clusterTolerations:
    - {key: cluster.karmada.io/not-ready,   operator: Exists, effect: NoExecute, tolerationSeconds: 30}
    - {key: cluster.karmada.io/unreachable, operator: Exists, effect: NoExecute, tolerationSeconds: 30}
    replicaScheduling:
      replicaSchedulingType: Divided
      replicaDivisionPreference: Weighted
EOF

echo "== wait for initial spread across both members =="
for i in $(seq 1 24); do
  a=$(kubectl --context kind-$MA -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  b=$(kubectl --context kind-$MB -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  echo "  t=${i}0s  member-a=$a  member-b=$b"
  [ "$a" -ge 1 ] && [ "$b" -ge 1 ] && break
  sleep 10
done
echo "BEFORE failover: member-a=$a member-b=$b (expect ~2 + ~2)"

echo "== KILL member-a (docker stop its node) -> trigger failover =="
docker stop ${MA}-control-plane >/dev/null
echo "member-a stopped at $(date +%T); watching member-b for rescheduled replicas..."
for i in $(seq 1 18); do
  sleep 15
  b=$(kubectl --context kind-$MB -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  cl=$(K get cluster $MA -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  echo "  +$((i*15))s  member-b pods=$b  member-a Ready=$cl"
  [ "$b" -ge 4 ] && break
done
echo "AFTER failover: member-b=$b (expect 4 = all replicas rescheduled)"
K get rb -n astra-ide 2>/dev/null | tail -3
echo "FAILOVER_DONE member_b_final=$b"
