#!/usr/bin/env bash
for i in $(seq 1 18); do
  sleep 30
  echo "[t=$((i*30))s] $(tail -1 /tmp/karmada.log 2>/dev/null)"
  if ! pgrep -f karmada-continue >/dev/null; then echo "FINISHED"; break; fi
done
echo "=== last 25 log lines ==="; tail -25 /tmp/karmada.log 2>/dev/null
