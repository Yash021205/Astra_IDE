#!/usr/bin/env bash
# Why didn't the NoExecute eviction fire? Check the controller's actual running
# command + enabled controllers + logs.
HC=kind-karmada-host
echo "== controller-manager pod (restarts) =="
kubectl --context "$HC" -n karmada-system get pods -l app=karmada-controller-manager --no-headers
echo "== RUNNING pod command (failover/eviction/controllers flags) =="
kubectl --context "$HC" -n karmada-system get pod -l app=karmada-controller-manager \
  -o jsonpath='{.items[0].spec.containers[0].command}' | tr ',' '\n' \
  | grep -iE 'no-execute|eviction|feature|controllers|taint' || echo '(no such flags)'
echo "== does this karmada-controller-manager support the flag? =="
kubectl --context "$HC" -n karmada-system exec deploy/karmada-controller-manager -- \
  /bin/karmada-controller-manager --help 2>&1 | grep -iE 'no-execute-taint|failover-eviction|^ *--controllers' | head -5
echo "== controller logs: taint/evict/flag errors =="
kubectl --context "$HC" -n karmada-system logs -l app=karmada-controller-manager --tail=500 2>/dev/null \
  | grep -iE 'taint|evict|no-execute|unknown flag|invalid' | tail -8
