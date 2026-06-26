#!/usr/bin/env bash
# Close B2 (Tetragon event capture) + produce a first-party syscall corpus for
# the B4 IDS. Installs Tetragon, hooks a RICH set of syscalls, runs THREE
# workloads with genuinely different syscall vocabularies (network / file-IO /
# process-spawn) so the 3-stage IDS can actually separate the classes, then
# captures real in-kernel events via the tetra gRPC API to JSON.
set -uo pipefail
CTX=kind-tetra
echo "== (re)create kind cluster =="
kind delete cluster --name tetra >/dev/null 2>&1 || true
kind create cluster --name tetra --wait 120s

echo "== install Tetragon (eBPF) =="
helm repo add cilium https://helm.cilium.io >/dev/null 2>&1
helm repo update >/dev/null 2>&1
helm install tetragon cilium/tetragon -n kube-system --kube-context "$CTX" --wait --timeout 5m >/dev/null 2>&1
kubectl --context "$CTX" -n kube-system rollout status ds/tetragon --timeout=180s | tail -1

echo "== apply RICH syscall TracingPolicy =="
cat <<EOF | kubectl --context "$CTX" apply -f - 2>&1 | tail -1
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata: {name: astra-syscalls}
spec:
  kprobes:
    - {call: "sys_openat",     syscall: true}
    - {call: "sys_read",       syscall: true}
    - {call: "sys_write",      syscall: true}
    - {call: "sys_close",      syscall: true}
    - {call: "sys_execve",     syscall: true}
    - {call: "sys_clone",      syscall: true}
    - {call: "sys_socket",     syscall: true}
    - {call: "sys_connect",    syscall: true}
    - {call: "sys_sendto",     syscall: true}
    - {call: "sys_recvfrom",   syscall: true}
    - {call: "sys_mmap",       syscall: true}
    - {call: "sys_newfstatat", syscall: true}
EOF

echo "== deploy 3 distinct workloads (distinct syscall vocabularies) =="
# wl1 NETWORK: DNS lookups -> socket/connect/sendto/recvfrom
kubectl --context "$CTX" run wl1 --image=busybox:1.36 --restart=Never -- \
  sh -c 'while true; do nslookup kubernetes.default >/dev/null 2>&1; done' 2>/dev/null
# wl2 FILE-IO: walk + read many files -> openat/read/newfstatat/close/mmap
kubectl --context "$CTX" run wl2 --image=busybox:1.36 --restart=Never -- \
  sh -c 'while true; do find /usr /etc -type f 2>/dev/null | head -40 | xargs -r cat >/dev/null 2>&1; done' 2>/dev/null
# wl3 PROCESS-SPAWN: fork/exec many short children -> execve/clone heavy
kubectl --context "$CTX" run wl3 --image=busybox:1.36 --restart=Never -- \
  sh -c 'while true; do for i in 1 2 3 4 5 6 7 8; do /bin/true; done; done' 2>/dev/null
sleep 30

echo "== capture real syscall events (tetra getevents -> JSON) =="
TET=$(kubectl --context "$CTX" -n kube-system get pods -l app.kubernetes.io/name=tetragon -o name | head -1); TET=${TET#pod/}
timeout 30 kubectl --context "$CTX" -n kube-system exec "$TET" -c tetragon -- tetra getevents -o json > /tmp/corpus.json 2>/dev/null || true
sleep 2
echo "== RESULTS =="
echo "total events captured : $(wc -l < /tmp/corpus.json 2>/dev/null || echo 0)"
echo "syscall (kprobe) events: $(grep -c process_kprobe /tmp/corpus.json 2>/dev/null || echo 0)"
echo "distinct syscalls seen :"; grep -oE '"function_name":"[^"]*"' /tmp/corpus.json 2>/dev/null | sort | uniq -c | sort -rn | head -14
echo "CORPUS_DONE"
