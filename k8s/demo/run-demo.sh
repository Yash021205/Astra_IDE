#!/usr/bin/env bash
#
# ASTRA-IDE multi-cluster demo: spin up a fresh Karmada federation on three kind
# clusters, propagate workspace pods across the members, install Tetragon (eBPF)
# on a member, and capture a live failover. Idempotent and self-contained: it
# recreates from scratch so it works reliably even after a VM reboot (kind
# clusters do not survive Docker restarts cleanly).
#
# Run on the Linux VM (needs docker, kind, kubectl, karmadactl, helm):
#   bash k8s/demo/run-demo.sh          # full spin-up + capture
#   bash k8s/demo/run-demo.sh capture  # just re-capture from a running federation
#   bash k8s/demo/run-demo.sh down     # delete the three clusters
#
# Captured evidence lands in k8s/demo/captures/ (git-ignored) for the slides.
set -uo pipefail

HOST=karmada-host
MEMBERS=(member-a member-b)
NS=astra-ide
KARMADA_CONF="$HOME/karmada-apiserver.config"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAP="$HERE/captures"
mkdir -p "$CAP"

log(){ printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
kh(){ kubectl --context "kind-$HOST" "$@"; }        # host cluster
km(){ local c="$1"; shift; kubectl --context "kind-$c" "$@"; }  # member cluster
kk(){ kubectl --kubeconfig "$KARMADA_CONF" "$@"; }  # karmada control plane

# ── down ─────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "down" ]]; then
  for c in "$HOST" "${MEMBERS[@]}"; do kind delete cluster --name "$c" 2>/dev/null; done
  echo "deleted clusters"; exit 0
fi

# ── capture-only ─────────────────────────────────────────────────────────────
capture(){
  log "Federation members"; kk get clusters -o wide 2>&1 | tee "$CAP/01-clusters.txt"
  log "Propagated workspace pods (per member)"
  for c in "${MEMBERS[@]}"; do
    echo "--- $c ---"; km "$c" get pods -n "$NS" -o wide 2>/dev/null
  done | tee "$CAP/02-workspace-pods.txt"
  log "Tetragon eBPF events (sample, member-a)"
  km member-a exec -n kube-system ds/tetragon -c tetragon -- \
     tetra getevents -o compact --pods "" 2>/dev/null | head -25 | tee "$CAP/03-tetragon-events.txt" \
     || echo "tetragon not installed yet" | tee "$CAP/03-tetragon-events.txt"
}
if [[ "${1:-}" == "capture" ]]; then capture; exit 0; fi

# ── 1. three kind clusters ───────────────────────────────────────────────────
for c in "$HOST" "${MEMBERS[@]}"; do
  if kind get clusters 2>/dev/null | grep -qx "$c"; then
    echo "kind cluster $c already exists"
  else
    log "Creating kind cluster $c"; kind create cluster --name "$c" --wait 90s
  fi
done

# ── 2. Karmada control plane on the host ─────────────────────────────────────
if kk get clusters >/dev/null 2>&1; then
  echo "Karmada control plane already reachable"
else
  log "Installing Karmada control plane on $HOST"
  karmadactl init --kubeconfig "$HOME/.kube/config" --context "kind-$HOST" \
    --karmada-apiserver-advertise-address 127.0.0.1 \
    --kubeconfig-path "$KARMADA_CONF" 2>&1 | tail -20
fi

# ── 3. join the members ──────────────────────────────────────────────────────
for c in "${MEMBERS[@]}"; do
  if kk get cluster "$c" >/dev/null 2>&1; then
    echo "member $c already joined"
  else
    log "Joining member $c to Karmada"
    karmadactl join "$c" --kubeconfig "$KARMADA_CONF" \
      --cluster-kubeconfig "$HOME/.kube/config" --cluster-context "kind-$c" 2>&1 | tail -5
  fi
done

# ── 4. deploy workspaces + propagation policy ────────────────────────────────
log "Applying workspace deployment + PropagationPolicy through Karmada"
kk create namespace "$NS" 2>/dev/null || true
kk apply -f "$HERE/../base/namespace.yaml" 2>/dev/null || true
kk apply -f "$HERE/workspace-deployment.yaml"
kk apply -f "$HERE/propagation.yaml"
sleep 20

# ── 5. Tetragon (eBPF) on member-a ───────────────────────────────────────────
if ! km member-a get ds -n kube-system tetragon >/dev/null 2>&1; then
  log "Installing Tetragon (eBPF) on member-a"
  helm repo add cilium https://helm.cilium.io >/dev/null 2>&1 || true
  helm repo update >/dev/null 2>&1
  helm --kube-context kind-member-a install tetragon cilium/tetragon -n kube-system 2>&1 | tail -4
  km member-a rollout status ds/tetragon -n kube-system --timeout=120s 2>/dev/null
  km member-a apply -f "$HERE/../base/eBPF-tetragon-policy.yaml" 2>/dev/null || true
fi

# ── 6. capture baseline, then a live failover ────────────────────────────────
capture

log "FAILOVER: cordoning + draining member-a, watch pods reschedule to member-b"
kk cordon cluster member-a 2>/dev/null || \
  karmadactl taint clusters member-a failover=demo:NoExecute --kubeconfig "$KARMADA_CONF" 2>/dev/null
{
  echo "t=0  (member-a marked unschedulable)"
  for t in 10 20 30 45 60; do
    sleep $((t == 10 ? 10 : 10))
    echo "--- t=${t}s : member-b workspace pods ---"
    km member-b get pods -n "$NS" -o wide 2>/dev/null | grep -c Running | xargs echo "running on member-b:"
  done
} | tee "$CAP/04-failover.txt"

log "DONE. Evidence captured in $CAP :"
ls -1 "$CAP"
echo "Uncordon with: karmadactl uncordon cluster member-a --kubeconfig $KARMADA_CONF"
