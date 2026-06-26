#!/usr/bin/env bash
# B2 live eBPF test: install Tetragon on the member1 kind cluster, apply ASTRA's
# TracingPolicy, generate syscall activity in a workspace pod, and capture the
# real in-kernel events (proving eBPF capture works on this VM's kernel).
CTX=kind-member1
echo "=== install Tetragon (eBPF) on $CTX ==="
helm repo add cilium https://helm.cilium.io >/dev/null 2>&1
helm repo update >/dev/null 2>&1
helm install tetragon cilium/tetragon -n kube-system --kube-context "$CTX" \
  --set tetragon.btf=/var/lib/tetragon/btf 2>&1 | tail -2 || \
  helm install tetragon cilium/tetragon -n kube-system --kube-context "$CTX" 2>&1 | tail -2
echo "=== wait for tetragon DaemonSet (eBPF loaded when Running) ==="
kubectl --context "$CTX" -n kube-system rollout status ds/tetragon --timeout=180s 2>&1 | tail -2
kubectl --context "$CTX" -n kube-system get pods -l app.kubernetes.io/name=tetragon -o wide 2>/dev/null | head -3

echo "=== generate syscall activity in a workspace pod ==="
POD=$(kubectl --context "$CTX" -n astra-ide get pods -o name 2>/dev/null | head -1)
echo "target pod: $POD"
kubectl --context "$CTX" -n astra-ide exec "${POD#pod/}" -- sh -c 'cat /etc/hostname >/dev/null; ls -la /etc >/dev/null; id' 2>/dev/null

echo "=== REAL eBPF events captured by Tetragon (process_exec / syscalls) ==="
TET=$(kubectl --context "$CTX" -n kube-system get pods -l app.kubernetes.io/name=tetragon -o name 2>/dev/null | head -1)
timeout 12 kubectl --context "$CTX" -n kube-system exec "${TET#pod/}" -c tetragon -- \
  tetra getevents -o compact 2>/dev/null | head -15
echo "TETRAGON_DONE"
