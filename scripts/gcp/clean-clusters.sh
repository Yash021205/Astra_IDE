#!/usr/bin/env bash
pkill -f run-federation-scale 2>/dev/null
sleep 2
for c in $(kind get clusters 2>/dev/null); do
  echo "deleting cluster: $c"
  kind delete cluster --name "$c"
done
echo "remaining clusters: $(kind get clusters 2>/dev/null | wc -l)"
echo "running containers: $(docker ps -q | wc -l)"
echo "CLEAN_DONE"
