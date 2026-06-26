#!/usr/bin/env bash
# Enable Karmada NoExecute cluster-taint eviction (v1.18) on the live setup,
# then re-fail member-a and watch its replicas reschedule onto member-b.
set -uo pipefail
HC=kind-karmada-host
KCFG=$HOME/karmada-apiserver.config
K() { kubectl --kubeconfig "$KCFG" "$@"; }

echo "== patch karmada-controller-manager: enable no-execute taint eviction =="
kubectl --context $HC -n karmada-system patch deploy karmada-controller-manager --type=json -p '[
  {"op":"add","path":"/spec/template/spec/containers/0/command/-","value":"--enable-no-execute-taint-eviction=true"},
  {"op":"add","path":"/spec/template/spec/containers/0/command/-","value":"--failover-eviction-timeout=30s"}]' | tail -1
kubectl --context $HC -n karmada-system rollout status deploy/karmada-controller-manager --timeout=150s | tail -1

echo "== bring member-a back so we can fail it cleanly under the new config =="
docker start member-a-control-plane >/dev/null; sleep 8
for i in $(seq 1 20); do
  r=$(K get cluster member-a -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  echo "  member-a Ready=$r"; [ "$r" = "True" ] && break; sleep 6
done
echo "spread before re-kill:"; K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}'; echo

echo "== KILL member-a (docker stop) under NoExecute eviction =="
docker stop member-a-control-plane >/dev/null; echo "stopped at $(date +%T)"
for i in $(seq 1 20); do
  sleep 15
  taint=$(K get cluster member-a -o jsonpath='{.spec.taints[*].effect}' 2>/dev/null)
  spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)
  b=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  echo "  +$((i*15))s taint=[$taint] member-b_pods=$b spread=$spread"
  echo "$spread" | grep -q '"member-b","replicas":4' && { echo RESCHEDULED_OK; break; }
done
echo "FIX_DONE final_spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)"
