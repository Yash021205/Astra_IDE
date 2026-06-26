#!/usr/bin/env bash
# Demonstrate the eviction+reschedule itself. v1.18 auto-taints a failed cluster
# only NoSchedule (safety default); --enable-no-execute-taint-eviction makes the
# controller ACT on a NoExecute taint. Applying that taint (the operator action
# the flag is designed for) triggers graceful eviction off member-a and
# reschedule onto member-b.
set -uo pipefail
KCFG=$HOME/karmada-apiserver.config
K() { kubectl --kubeconfig "$KCFG" "$@"; }

echo "== ensure member-a is failed =="
docker stop member-a-control-plane 2>/dev/null || true; sleep 3
echo "spread now: $(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}')"

echo "== apply NoExecute taint to member-a (operator failover action) =="
K patch cluster member-a --type=merge \
  -p '{"spec":{"taints":[{"key":"cluster.karmada.io/not-ready","effect":"NoExecute"}]}}'
echo "taints now: $(K get cluster member-a -o jsonpath='{.spec.taints}')"

echo "== watch graceful eviction -> reschedule onto member-b =="
for i in $(seq 1 30); do
  sleep 10
  spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)
  taint=$(K get cluster member-a -o jsonpath='{.spec.taints[*].effect}' 2>/dev/null)
  b=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  echo "  +$((i*10))s taint=[$taint] member-b_pods=$b spread=$spread"
  echo "$spread" | grep -q '"member-b","replicas":4' && { echo RESCHEDULED_OK; break; }
done
echo "FINAL spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)"
echo "FINAL member-b pods=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)"
echo "FIX4_DONE"
