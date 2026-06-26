#!/usr/bin/env bash
# Continue the federation setup assuming the kind clusters already exist
# (karmada-host + member1..N). Inits Karmada, joins members, propagates an ASTRA
# workspace Deployment across all N, then runs the two edge cases.
set -uo pipefail
N="${N:-5}"
echo "== Karmada continue: host + $N members (clusters assumed up) =="

kubectl config use-context kind-karmada-host

echo "== karmadactl init (sudo: init manages /etc/karmada as root) =="
sudo rm -rf /etc/karmada
sudo karmadactl init --kubeconfig "$HOME/.kube/config" || { echo "INIT_FAILED"; exit 1; }
sudo chown -R "$(id -u):$(id -g)" /etc/karmada     # so joins (as user) can read the config
KCFG=$(ls /etc/karmada/karmada-apiserver.config "$HOME/.kube/karmada-apiserver.config" "$HOME/.kube/karmada.config" 2>/dev/null | head -1)
[ -z "$KCFG" ] && { echo "FATAL: karmada config not found"; exit 1; }
echo "karmada config: $KCFG"

echo "== join $N members =="
for i in $(seq 1 "$N"); do
  karmadactl --kubeconfig "$KCFG" join "member$i" \
    --cluster-kubeconfig="$HOME/.kube/config" --cluster-context="kind-member$i" || echo "join member$i: $?"
done
echo "== registered clusters =="; kubectl --kubeconfig "$KCFG" get clusters

echo "== namespace + N-way PropagationPolicy + workspace Deployment =="
kubectl --kubeconfig "$KCFG" create namespace astra-ide 2>/dev/null || true
MEMBERS=$(seq 1 "$N" | sed 's/^/member/' | paste -sd, -)
cat <<EOF | kubectl --kubeconfig "$KCFG" apply -f -
apiVersion: policy.karmada.io/v1alpha1
kind: PropagationPolicy
metadata: {name: ws-scale, namespace: astra-ide}
spec:
  resourceSelectors: [{apiVersion: apps/v1, kind: Deployment, labelSelector: {matchLabels: {app: astra-workspace}}}]
  placement:
    clusterAffinity: {clusterNames: [${MEMBERS}]}
    replicaScheduling: {replicaSchedulingType: Divided, replicaDivisionPreference: Weighted}
    clusterTolerations:
      - {key: cluster.karmada.io/not-ready, operator: Exists, effect: NoExecute, tolerationSeconds: 20}
      - {key: cluster.karmada.io/unreachable, operator: Exists, effect: NoExecute, tolerationSeconds: 20}
EOF
kubectl --kubeconfig "$KCFG" -n astra-ide create deployment astra-workspace --image=nginx:alpine --replicas="$((N*2))" 2>/dev/null || true
kubectl --kubeconfig "$KCFG" -n astra-ide label deployment astra-workspace app=astra-workspace --overwrite

echo "== EDGE CASE 1: replicas spread across all $N members =="
sleep 25
for i in $(seq 1 "$N"); do printf "member%s pods: " "$i"; kubectl --context "kind-member$i" -n astra-ide get pods --no-headers 2>/dev/null | wc -l; done

echo "== EDGE CASE 2: kill member1, watch Karmada migrate its share =="
docker stop member1-control-plane >/dev/null
echo "   waiting 50s for reschedule (tolerationSeconds=20)..."; sleep 50
for i in $(seq 2 "$N"); do printf "member%s pods AFTER: " "$i"; kubectl --context "kind-member$i" -n astra-ide get pods --no-headers 2>/dev/null | wc -l; done
echo "CONTINUE_DONE"
