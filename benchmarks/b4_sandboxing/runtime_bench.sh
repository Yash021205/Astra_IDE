#!/usr/bin/env bash
# B4 runtime overhead benchmark — run on the Linux node (see RUNTIME_TESTING.md).
# Measures, per runtime: container startup latency, a syscall-heavy microbench,
# and a CPU loop. Compares runc (baseline) vs gVisor (runsc) vs Firecracker.
#
# runc + gvisor are measured via `docker run --runtime=`; Firecracker is measured
# via kubectl (Kata RuntimeClass) when a cluster is reachable, else skipped with
# a note. Safe to re-run; creates no persistent state.
set -uo pipefail

REPS="${REPS:-10}"
IMAGE="${IMAGE:-alpine:3.19}"
# syscall-heavy: 200k stat() calls; CPU: 5M integer ops. Pure shell so it runs in
# a bare alpine with no extra packages.
SYSCALL_CMD='i=0; while [ $i -lt 200000 ]; do stat /etc/hostname >/dev/null 2>&1; i=$((i+1)); done'
CPU_CMD='i=0; s=0; while [ $i -lt 5000000 ]; do s=$((s+i)); i=$((i+1)); done; echo $s'

_have() { command -v "$1" >/dev/null 2>&1; }

# median of REPS timings (ms) for: docker run --runtime=$1 $IMAGE sh -c "$2"
bench_docker() {
  local rt="$1" cmd="$2" t times=()
  for _ in $(seq "$REPS"); do
    t=$( { /usr/bin/time -f '%e' docker run --rm --runtime="$rt" "$IMAGE" \
           sh -c "$cmd" >/dev/null; } 2>&1 )
    times+=("$t")
  done
  printf '%s\n' "${times[@]}" | sort -n | awk '{a[NR]=$1} END{print a[int(NR/2)+1]}'
}

row() { printf '  %-14s startup=%-8s syscall=%-8s cpu=%-8s\n' "$1" "$2" "$3" "$4"; }

echo "== B4 runtime overhead (median of $REPS, seconds) =="
if _have docker; then
  for rt in runc runsc; do
    label=$([ "$rt" = runsc ] && echo "gvisor" || echo "runc")
    if docker run --rm --runtime="$rt" "$IMAGE" true >/dev/null 2>&1; then
      su=$(bench_docker "$rt" "true")
      sy=$(bench_docker "$rt" "$SYSCALL_CMD")
      cp=$(bench_docker "$rt" "$CPU_CMD")
      row "$label" "$su" "$sy" "$cp"
    else
      row "$label" "n/a" "n/a" "n/a"
      echo "     ($rt runtime not registered with docker — see RUNTIME_TESTING.md §1)"
    fi
  done
else
  echo "  docker not found — install it or use the kubectl path below."
fi

echo
echo "== Firecracker (Kata) — via kubectl, needs cluster + /dev/kvm =="
if _have kubectl && kubectl get runtimeclass firecracker >/dev/null 2>&1; then
  start=$(date +%s.%N)
  kubectl run fc-bench --rm -i --restart=Never --image="$IMAGE" \
    --overrides='{"spec":{"runtimeClassName":"firecracker"}}' \
    -- sh -c "$CPU_CMD" >/dev/null 2>&1
  end=$(date +%s.%N)
  printf '  firecracker    pod round-trip (boot+run+teardown) = %.2fs\n' \
    "$(echo "$end - $start" | bc)"
  echo "  (compare boot-to-app against Agache NSDI 2020: <125 ms)"
else
  echo "  kubectl/firecracker RuntimeClass not available — run on the cluster node."
fi

echo
echo "Compare against docs/research/01-adaptive-sandboxing.md §1.1:"
echo "  gVisor syscall overhead ~10-40% (median ~18%) vs runc; Firecracker CPU >95%."
