#!/usr/bin/env bash
# Root cause: --failover-eviction-timeout is NOT a valid v1.18 flag -> controller
# CrashLoopBackOff. Remove it, keep the valid --enable-no-execute-taint-eviction,
# let the controller go healthy, then fail member-a and watch the reschedule.
set -uo pipefail
HC=kind-karmada-host
KCFG=$HOME/karmada-apiserver.config
K() { kubectl --kubeconfig "$KCFG" "$@"; }

echo "== stop the previous fix loop =="
pkill -f karmada-fix2.sh 2>/dev/null || true; sleep 2

echo "== remove the invalid --failover-eviction-timeout flag =="
idx=$(kubectl --context "$HC" -n karmada-system get deploy karmada-controller-manager \
  -o jsonpath='{.spec.template.spec.containers[0].command}' | tr ',' '\n' \
  | grep -n 'failover-eviction-timeout' | head -1 | cut -d: -f1)
if [ -n "${idx:-}" ]; then
  kubectl --context "$HC" -n karmada-system patch deploy karmada-controller-manager --type=json \
    -p "[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/command/$((idx-1))\"}]" | tail -1
else
  echo "  (flag already gone)"
fi

echo "== wait for a healthy 1/1 Running controller =="
for i in $(seq 1 30); do
  line=$(kubectl --context "$HC" -n karmada-system get pods -l app=karmada-controller-manager --no-headers 2>/dev/null)
  echo "  $(echo "$line" | tr '\n' ' ')"
  if echo "$line" | grep -q '1/1 *Running' && [ "$(echo "$line" | grep -vc '1/1 *Running')" -eq 0 ]; then break; fi
  sleep 6
done
echo "flags in running controller:"
kubectl --context "$HC" -n karmada-system get pod -l app=karmada-controller-manager \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.containers[0].command}' \
  | tr ',' '\n' | grep -iE 'no-execute' || echo '  (missing!)'

echo "== bring member-a back, wait both clusters Ready =="
docker start member-a-control-plane >/dev/null; sleep 8
for i in $(seq 1 25); do
  a=$(K get cluster member-a -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  b=$(K get cluster member-b -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  echo "  member-a=$a member-b=$b"
  [ "$a" = "True" ] && [ "$b" = "True" ] && break; sleep 6
done
echo "spread before kill: $(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}')"

echo "== KILL member-a (NoExecute eviction should now reschedule) =="
docker stop member-a-control-plane >/dev/null; echo "killed at $(date +%T)"
for i in $(seq 1 24); do
  sleep 15
  taint=$(K get cluster member-a -o jsonpath='{.spec.taints[*].effect}' 2>/dev/null)
  spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)
  b=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  echo "  +$((i*15))s taint=[$taint] member-b_pods=$b spread=$spread"
  echo "$spread" | grep -q '"member-b","replicas":4' && { echo RESCHEDULED_OK; break; }
done
echo "DONE3 final=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)"
