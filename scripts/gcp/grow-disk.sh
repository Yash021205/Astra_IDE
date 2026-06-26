#!/usr/bin/env bash
set -e
echo "=== before ==="; df -h / | sed -n '2p'
if ! command -v growpart >/dev/null; then
  echo "=== install cloud-guest-utils (growpart) ==="
  sudo apt-get update -qq && sudo apt-get install -y -qq cloud-guest-utils gdisk
fi
echo "=== grow partition + fs ==="
sudo growpart /dev/sda 1
sudo resize2fs /dev/sda1
echo "=== after ==="; df -h / | sed -n '2p'
echo "GROW_DONE"
