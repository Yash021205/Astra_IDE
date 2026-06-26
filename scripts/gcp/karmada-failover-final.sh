#!/usr/bin/env bash
# Finish + verify Karmada cluster failover reschedule.
#
# v1.18 finding: the cluster-status controller only auto-adds a NoSchedule taint
# on failure; --enable-no-execute-taint-eviction makes the controller ACT on a
# NoExecute taint (Gracefully: schedule to a healthy cluster, then purge). So we
# apply the NoExecute taint (the operator failover action) and, because the
# status controller may normalise it back, we re-assert it until the scheduler
# has moved the replicas onto member-b.
set -uo pipefail
HC=kind-karmada-host
KCFG=$HOME/karmada-apiserver.config
K() { kubectl --kubeconfig "$KCFG" "$@"; }

echo "===== STATE BEFORE ====="
K get clusters 2>/dev/null
echo "controller flags:"
kubectl --context "$HC" -n karmada-system get deploy karmada-controller-manager \
  -o jsonpath='{.spec.template.spec.containers[0].command}' 2>/dev/null | tr ',' '\n' | grep -i no-execute || echo "  (no flag!)"
echo "rb spread now: $(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)"

echo "===== ensure member-a is failed ====="
docker stop member-a-control-plane >/dev/null 2>&1 || true
sleep 5

echo "===== apply + hold NoExecute taint, watch reschedule ====="
killed=$(date +%s)
for i in $(seq 1 24); do
  # (re)assert the NoExecute taint in case the status controller normalised it
  K patch cluster member-a --type=merge \
    -p '{"spec":{"taints":[{"key":"cluster.karmada.io/not-ready","effect":"NoExecute","value":""}]}}' >/dev/null 2>&1 || true
  sleep 10
  taint=$(K get cluster member-a -o jsonpath='{.spec.taints[*].effect}' 2>/dev/null)
  spread=$(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)
  bpods=$(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)
  echo "  +$(( $(date +%s) - killed ))s taint=[$taint] member-b_pods=$bpods spread=$spread"
  if echo "$spread" | grep -q '"member-b","replicas":4'; then echo "RESCHEDULED_OK"; break; fi
  if echo "$spread" | grep -vq 'member-a'; then echo "RESCHEDULED_OK (member-a dropped)"; break; fi
done

echo "===== STATE AFTER ====="
echo "final rb spread: $(K -n astra-ide get rb astra-ws-deployment -o jsonpath='{.spec.clusters}' 2>/dev/null)"
echo "member-b pods:   $(kubectl --context kind-member-b -n astra-ide get pods --no-headers 2>/dev/null | grep -c .)"
K -n astra-ide get rb astra-ws-deployment -o jsonpath='{range .status.aggregatedStatus[*]}{.clusterName}={.applied}{"\n"}{end}' 2>/dev/null
echo "FINAL_DONE"
