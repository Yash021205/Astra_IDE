#!/usr/bin/env bash
# B5 — N-cluster Karmada federation SCALE + edge-case test.
# Stands up 1 Karmada host + N member kind clusters, joins them, propagates
# ASTRA workspaces across all N, then exercises edge cases: saturation spread and
# cluster-failure migration. Run on a Linux box with enough RAM (see sizing).
#
#   N=6 bash run-federation-scale.sh
#
# Sizing: each kind cluster ≈ 1 GB + Karmada control plane ≈ 2-3 GB + Tetragon.
# N=6 needs ~12-13 GB → GCP e2-standard-8 (32 GB) recommended (resize back after).
set -euo pipefail
N="${N:-6}"                         # number of member clusters
IMG="${IMG:-nginx:alpine}"          # lightweight workload image
echo "== Karmada scale test: 1 host + $N members =="

# 0. prereqs check
for t in docker kind kubectl karmadactl; do command -v "$t" >/dev/null || { echo "missing $t"; exit 1; }; done

# 0b. raise inotify limits — REQUIRED to run many kind clusters (each runs systemd
# and consumes inotify instances; the default ~128 is exhausted past ~2 clusters,
# giving "could not find a log line that matches Reached target Multi-User System").
sudo sysctl -w fs.inotify.max_user_watches=1048576 >/dev/null
sudo sysctl -w fs.inotify.max_user_instances=8192 >/dev/null
sudo sysctl -w kernel.keys.maxkeys=2000 >/dev/null 2>&1 || true
echo "inotify limits raised: instances=$(cat /proc/sys/fs/inotify/max_user_instances)"

# 1. host + N member clusters
kind create cluster --name karmada-host --wait 120s
for i in $(seq 1 "$N"); do kind create cluster --name "member$i" --wait 120s; done

# 2. Karmada control plane on the host. `karmadactl init` manages /etc/karmada as
# root, so run it with sudo, then chown the output so member joins (as the user)
# can read the generated karmada-apiserver config.
kubectl config use-context kind-karmada-host
sudo rm -rf /etc/karmada
sudo karmadactl init --kubeconfig "$HOME/.kube/config"
sudo chown -R "$(id -u):$(id -g)" /etc/karmada
# locate the karmada-apiserver kubeconfig (path varies by version)
KCFG=$(ls /etc/karmada/karmada-apiserver.config \
          "$HOME/.kube/karmada-apiserver.config" \
          "$HOME/.kube/karmada.config" 2>/dev/null | head -1)
[ -z "$KCFG" ] && { echo "FATAL: karmada apiserver config not found after init"; exit 1; }
echo "karmada config: $KCFG"

# 3. join all members
for i in $(seq 1 "$N"); do
  karmadactl --kubeconfig "$KCFG" join "member$i" \
    --cluster-kubeconfig="$HOME/.kube/config" --cluster-context="kind-member$i"
done
echo "== registered clusters =="; kubectl --kubeconfig "$KCFG" get clusters

# 4. namespace + an N-way PropagationPolicy + a workspace Deployment
kubectl --kubeconfig "$KCFG" create namespace astra-ide || true
MEMBERS=$(seq 1 "$N" | sed 's/^/member/' | paste -sd, -)
cat <<EOF | kubectl --kubeconfig "$KCFG" apply -f -
apiVersion: policy.karmada.io/v1alpha1
kind: PropagationPolicy
metadata: {name: ws-scale, namespace: astra-ide}
spec:
  resourceSelectors: [{apiVersion: apps/v1, kind: Deployment, labelSelector: {matchLabels: {app: astra-workspace}}}]
  placement:
    clusterAffinity: {clusterNames: [$(seq 1 $N | sed 's/^/member/' | paste -sd, -)]}
    replicaScheduling: {replicaSchedulingType: Divided, replicaDivisionPreference: Weighted}
    clusterTolerations:
      - {key: cluster.karmada.io/not-ready, operator: Exists, effect: NoExecute, tolerationSeconds: 20}
      - {key: cluster.karmada.io/unreachable, operator: Exists, effect: NoExecute, tolerationSeconds: 20}
EOF
kubectl --kubeconfig "$KCFG" -n astra-ide create deployment astra-workspace \
  --image="$IMG" --replicas="$((N*2))" || true
kubectl --kubeconfig "$KCFG" -n astra-ide label deployment astra-workspace app=astra-workspace --overwrite

# 5. EDGE CASE 1 — saturation spread: replicas divided across ALL N clusters
sleep 20
echo "== replicas per member (should be spread across all $N) =="
for i in $(seq 1 "$N"); do
  printf "member%s: " "$i"; kubectl --context "kind-member$i" -n astra-ide get pods --no-headers 2>/dev/null | wc -l
done

# 6. EDGE CASE 2 — cluster-failure migration: kill member1, watch Karmada reschedule
echo "== killing member1 to test migration =="
docker stop member1-control-plane >/dev/null
echo "   waiting for Karmada to reschedule (tolerationSeconds=20)..."; sleep 45
echo "== replicas per member AFTER member1 failure (member1's share moved away) =="
for i in $(seq 2 "$N"); do
  printf "member%s: " "$i"; kubectl --context "kind-member$i" -n astra-ide get pods --no-headers 2>/dev/null | wc -l
done

echo "== DONE. Cleanup: kind delete clusters --all (or: for i in \$(seq 1 $N); do kind delete cluster --name member\$i; done; kind delete cluster --name karmada-host) =="
