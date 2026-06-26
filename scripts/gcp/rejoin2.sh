#!/usr/bin/env bash
# Correct kind+Karmada join: point member kubeconfigs at the member's CONTAINER IP
# on the 'kind' docker network (reachable from the host for `join` AND from the
# Karmada control-plane pods at runtime). Use insecure TLS to dodge SAN mismatch.
KCFG=/etc/karmada/karmada-apiserver.config
N="${N:-5}"

echo "=== host can reach a member container IP? ==="
IP2=$(docker inspect -f '{{.NetworkSettings.Networks.kind.IPAddress}}' member2-control-plane)
echo "member2 IP=$IP2"; curl -sk --max-time 4 "https://$IP2:6443/version" 2>&1 | head -2

echo "=== drop broken registrations + rejoin with container-IP kubeconfigs ==="
for i in $(seq 1 "$N"); do kubectl --kubeconfig "$KCFG" delete cluster "member$i" 2>/dev/null; done
sleep 3
for i in $(seq 1 "$N"); do
  IP=$(docker inspect -f '{{.NetworkSettings.Networks.kind.IPAddress}}' "member$i-control-plane")
  kind get kubeconfig --name "member$i" > "/tmp/m$i.config" 2>/dev/null
  kubectl --kubeconfig "/tmp/m$i.config" config unset "clusters.kind-member$i.certificate-authority-data" >/dev/null
  kubectl --kubeconfig "/tmp/m$i.config" config set-cluster "kind-member$i" --server="https://$IP:6443" --insecure-skip-tls-verify=true >/dev/null
  karmadactl --kubeconfig "$KCFG" join "member$i" --cluster-kubeconfig="/tmp/m$i.config" --cluster-context="kind-member$i" 2>&1 | tail -1
done

echo "=== wait for Ready (up to 120s) ==="
for t in $(seq 1 24); do
  ready=$(kubectl --kubeconfig "$KCFG" get clusters --no-headers 2>/dev/null | grep -cw True)
  echo "  Ready: $ready/$N"; [ "$ready" = "$N" ] && break; sleep 5
done
kubectl --kubeconfig "$KCFG" get clusters

echo "=== scale workspace=12, let Karmada divide across members ==="
kubectl --kubeconfig "$KCFG" -n astra-ide scale deployment astra-workspace --replicas=12
sleep 45
echo "=== EDGE CASE 1 — Running pods per member (sum ~12) ==="
tot=0
for i in $(seq 1 "$N"); do
  p=$(kubectl --context "kind-member$i" -n astra-ide get pods --no-headers 2>/dev/null | grep -c Running)
  printf "  member%s: %s\n" "$i" "$p"; tot=$((tot+p))
done
echo "  TOTAL across federation: $tot"
echo "REJOIN2_DONE"
