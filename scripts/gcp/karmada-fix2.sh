#!/usr/bin/env bash
# The flagged controller pod was stuck Pending (rolling update can't fit 2 on a
# 1-node kind cluster). Switch to Recreate so the flagged controller actually
# runs, then re-fail member-a and watch the NoExecute eviction reschedule.
set -uo pipefail
HC=kind-karmada-host
KCFG=$HOME/karmada-apiserver.config
K() { kubectl --kubeconfig "$KCFG" "$@"; }

echo "== force Recreate strategy so the flagged controller can start =="
kubectl --context "$HC" -n karmada-system patch deploy karmada-controller-manager \
  -p '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}' | tail -1
kubectl --context "$HC" -n karmada-system delete pod -l app=karmada-controller-manager --wait=false 2>/dev/null
for i in $(seq 1 25); do
  line=$(kubectl --context "$HC" -n karmada-system get pods -l app=karmada-controller-manager --no-headers 2>/dev/null)
  run=$(echo "$line" | grep -c '1/1.*Running')
  echo "  running=$run :: $(echo "$line" | tr '\n' ' ')"
  [ "$run" -ge 1 ] && [ "$(echo "$line" | grep -vc '1/1.*Running')" -eq 0 ] && break
  sleep 6
done
echo "flags in RUNNING controller:"
kubectl --context "$HC" -n karmada-system get pod -l app=karmada-controller-manager \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.containers[0].command}' \
  | tr ',' '\n' | grep -iE 'no-execute|eviction' || echo '  (flag NOT in running pod!)'

echo "== bring member-a back, then fail it under the flagged controller =="
docker start member-a-control-plane >/dev/null; sleep 8
for i in $(seq 1 20); do
  r=$(K get cluster member-a -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  echo "  member-a Ready=$r"; [ "$r" = "True" ] && break; sleep 6
done
echo "spread before kill: $(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}')"
docker stop member-a-control-plane >/dev/null; echo "killed at $(date +%T)"
for i in $(seq 1 20); do
  sleep 15
  taint=$(K get cluster member-a -o jsonpath='{.spec.taints[*].effect}' 2>/dev/null)
  spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)
  b=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  echo "  +$((i*15))s taint=[$taint] member-b_pods=$b spread=$spread"
  echo "$spread" | grep -q '"member-b","replicas":4' && { echo RESCHEDULED_OK; break; }
done
echo "DONE2 final=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)"
