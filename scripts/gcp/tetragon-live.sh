#!/usr/bin/env bash
CTX=kind-member1
TET=$(kubectl --context "$CTX" -n kube-system get pods -l app.kubernetes.io/name=tetragon -o name 2>/dev/null | head -1); TET=${TET#pod/}
POD=$(kubectl --context "$CTX" -n astra-ide get pods -o name 2>/dev/null | head -1); POD=${POD#pod/}
echo "tetragon=$TET workspace=$POD"
# background: generate syscall activity AFTER the stream starts
( sleep 4; for j in $(seq 1 10); do
    kubectl --context "$CTX" -n astra-ide exec "$POD" -- sh -c 'cat /etc/passwd >/dev/null; ls /usr/bin >/dev/null; id >/dev/null; date >/dev/null' 2>/dev/null
  done ) &
echo "=== LIVE in-kernel eBPF events (tetra getevents, RAW) ==="
kubectl --context "$CTX" -n kube-system exec "$TET" -c tetragon -- timeout 15 tetra getevents -o compact 2>/dev/null \
  | head -16
wait 2>/dev/null
echo "LIVE_DONE"
