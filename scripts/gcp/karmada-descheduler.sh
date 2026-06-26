#!/usr/bin/env bash
# Final piece of cluster failover: karmadactl init does NOT deploy the
# descheduler or per-member scheduler-estimators. Without them Karmada never
# re-evaluates replicas stuck on a failed cluster, so a NoExecute taint alone
# does not reschedule. Enable both, then fail member-a and verify the replicas
# move onto member-b.
set -uo pipefail
HC=kind-karmada-host
KCFG=$HOME/karmada-apiserver.config
HOSTCFG=$HOME/.kube/config
K() { kubectl --kubeconfig "$KCFG" "$@"; }

pkill -f kff.sh 2>/dev/null || true

echo "===== regenerate member kubeconfigs (container IP on shared kind net) ====="
docker start member-a-control-plane >/dev/null 2>&1 || true
sleep 8
for m in member-a member-b; do
  ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ${m}-control-plane 2>/dev/null)
  kind get kubeconfig --name "$m" > /tmp/${m}.config 2>/dev/null || true
  [ -n "$ip" ] && kubectl --kubeconfig /tmp/${m}.config config set-cluster "kind-${m}" \
      --server="https://${ip}:6443" --insecure-skip-tls-verify=true >/dev/null 2>&1 || true
done

echo "===== enable descheduler + scheduler-estimators ====="
karmadactl addons enable karmada-descheduler \
  --kubeconfig "$HOSTCFG" --karmada-kubeconfig "$KCFG" 2>&1 | tail -2 || true
for m in member-a member-b; do
  karmadactl addons enable karmada-scheduler-estimator \
    --kubeconfig "$HOSTCFG" --karmada-kubeconfig "$KCFG" \
    --member-kubeconfig /tmp/${m}.config --member-context "kind-${m}" 2>&1 | tail -1 || true
done
kubectl --context "$HC" -n karmada-system rollout status deploy/karmada-descheduler --timeout=150s 2>&1 | tail -1 || true
echo "karmada-system deployments:"
kubectl --context "$HC" -n karmada-system get deploy --no-headers 2>/dev/null | awk '{print "  "$1, $2}'

echo "===== fail member-a + NoExecute taint ====="
sleep 10
docker stop member-a-control-plane >/dev/null 2>&1 || true
echo "spread before: $(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}')"

echo "===== watch reschedule (descheduler interval ~2min) ====="
for i in $(seq 1 32); do
  K patch cluster member-a --type=merge \
    -p '{"spec":{"taints":[{"key":"cluster.karmada.io/not-ready","effect":"NoExecute","value":""}]}}' >/dev/null 2>&1 || true
  sleep 15
  spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)
  bpods=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  echo "  +$((i*15))s member-b_pods=$bpods spread=$spread"
  echo "$spread" | grep -q '"member-b","replicas":4' && { echo RESCHEDULED_OK; break; }
  echo "$spread" | grep -vq member-a && { echo "RESCHEDULED_OK (member-a dropped)"; break; }
done
echo "DESCHED_DONE final=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)"
echo "member-b pods: $(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)"
