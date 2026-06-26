#!/usr/bin/env bash
# Watch the federation run for up to ~9 min, printing progress; exit when done.
for i in $(seq 1 18); do
  sleep 30
  n=$(kind get clusters 2>/dev/null | wc -l)
  last=$(tail -1 /tmp/fed.log 2>/dev/null)
  echo "[t=$((i*30))s] kind_clusters=$n | $last"
  if ! pgrep -f run-federation-scale >/dev/null; then echo "SCRIPT_FINISHED"; break; fi
done
echo "=== last 6 log lines ==="; tail -6 /tmp/fed.log 2>/dev/null
