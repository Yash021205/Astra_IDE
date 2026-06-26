#!/usr/bin/env bash
CTX=kind-member1
TET=$(kubectl --context "$CTX" -n kube-system get pods -l app.kubernetes.io/name=tetragon -o name 2>/dev/null | head -1)
TET=${TET#pod/}
POD=$(kubectl --context "$CTX" -n astra-ide get pods -o name 2>/dev/null | head -1); POD=${POD#pod/}
echo "tetragon=$TET  workspace=$POD"

echo "=== stream Tetragon events to a file, THEN generate activity ==="
kubectl --context "$CTX" -n kube-system exec "$TET" -c tetragon -- \
  sh -c 'timeout 12 tetra getevents -o compact > /tmp/ev.txt 2>/dev/null' &
sleep 3
for j in 1 2 3 4; do
  kubectl --context "$CTX" -n astra-ide exec "$POD" -- sh -c 'cat /etc/passwd >/dev/null; ls -la /usr/bin >/dev/null; id >/dev/null; head -1 /etc/hostname' >/dev/null 2>&1
done
sleep 8
echo "=== REAL in-kernel eBPF events (process exec + syscalls in the workspace pod) ==="
kubectl --context "$CTX" -n kube-system exec "$TET" -c tetragon -- cat /tmp/ev.txt 2>/dev/null | grep -Ei "astra-workspace|process|exec|cat|ls|id " | head -12
echo "--- total events captured: $(kubectl --context "$CTX" -n kube-system exec "$TET" -c tetragon -- wc -l < /tmp/ev.txt 2>/dev/null) ---"
echo "CAPTURE_DONE"
