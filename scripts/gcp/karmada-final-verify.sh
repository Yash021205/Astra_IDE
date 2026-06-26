#!/usr/bin/env bash
# Deterministic failover verification: when the failed cluster (member-a) is
# removed from the federation, the always-running Karmada scheduler re-divides
# its replicas onto the surviving cluster (member-b). This is the core
# reschedule-on-cluster-loss guarantee, independent of the optional taint-
# eviction / descheduler timing.
set -uo pipefail
KCFG=$HOME/karmada-apiserver.config
K() { kubectl --kubeconfig "$KCFG" "$@"; }

pkill -f kd.sh 2>/dev/null || true; sleep 1

echo "===== BEFORE ====="
echo "clusters:"; K get clusters 2>/dev/null
echo "member-a node: $(docker ps -a --format '{{.Names}} {{.Status}}' | grep member-a-control-plane)"
echo "rb spread:     $(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}')"
echo "member-b pods: $(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)"

echo "===== FAIL + REMOVE member-a from the federation ====="
docker stop member-a-control-plane >/dev/null 2>&1 || true
# Remove the unreachable cluster from Karmada (operator/lifecycle action on a
# permanently failed member). --force because the member API is unreachable.
karmadactl unjoin member-a --kubeconfig "$KCFG" --force 2>&1 | tail -2 \
  || K delete cluster member-a --ignore-not-found 2>&1 | tail -1

echo "===== watch reschedule onto member-b ====="
for i in $(seq 1 24); do
  sleep 10
  spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)
  bpods=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  echo "  +$((i*10))s member-b_pods=$bpods spread=$spread"
  if echo "$spread" | grep -q '"member-b","replicas":4'; then echo "RESCHEDULED_OK (member-b now holds all 4)"; break; fi
  if ! echo "$spread" | grep -q 'member-a'; then echo "member-a removed from binding"; fi
done

echo "===== AFTER ====="
echo "clusters:";    K get clusters 2>/dev/null
echo "rb spread:     $(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}')"
echo "member-b pods: $(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)"
echo "VERIFY_DONE"
