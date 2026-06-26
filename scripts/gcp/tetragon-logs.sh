#!/usr/bin/env bash
CTX=kind-member1
TET=$(kubectl --context "$CTX" -n kube-system get pods -l app.kubernetes.io/name=tetragon -o name 2>/dev/null | head -1); TET=${TET#pod/}
echo "tetragon pod: $TET"
echo -n "containers: "; kubectl --context "$CTX" -n kube-system get pod "$TET" -o jsonpath='{.spec.containers[*].name}' 2>/dev/null; echo
POD=$(kubectl --context "$CTX" -n astra-ide get pods -o name 2>/dev/null | head -1); POD=${POD#pod/}
echo "workspace pod: $POD"

echo "=== generate syscall activity in the workspace pod ==="
for j in 1 2 3 4 5 6; do
  kubectl --context "$CTX" -n astra-ide exec "$POD" -- sh -c 'cat /etc/passwd >/dev/null; ls -la /usr/bin >/dev/null; id >/dev/null' 2>/dev/null
done
sleep 5

echo "=== REAL in-kernel eBPF events captured for the workspace pod (JSON) ==="
kubectl --context "$CTX" -n kube-system logs "$TET" -c export-stdout --tail=3000 2>/dev/null \
  | grep '"astra-workspace' | tail -6
echo "--- events mentioning the workspace pod: $(kubectl --context "$CTX" -n kube-system logs "$TET" -c export-stdout --tail=5000 2>/dev/null | grep -c '"astra-workspace') ---"
echo "=== sample process_exec binaries seen (proves syscall/exec capture) ==="
kubectl --context "$CTX" -n kube-system logs "$TET" -c export-stdout --tail=5000 2>/dev/null \
  | grep '"astra-workspace' | grep -oE '"binary":"[^"]*"' | sort | uniq -c | sort -rn | head -8
echo "LOGS_DONE"
