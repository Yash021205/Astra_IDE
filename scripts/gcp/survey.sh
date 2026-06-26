#!/usr/bin/env bash
# Survey the GCP VM for the Karmada + eBPF scale test.
set +e
echo "=== OS / kernel ==="
uname -r; grep PRETTY_NAME /etc/os-release
echo "=== RAM (MB) ==="
free -m | sed -n '1,2p'
echo "=== CPUs ==="; nproc
echo "=== BTF (eBPF CO-RE) ==="
ls -la /sys/kernel/btf/vmlinux 2>&1 | head -1
ls /sys/fs/bpf >/dev/null 2>&1 && echo "bpffs: present" || echo "bpffs: absent"
echo "=== tools ==="
for t in docker kind kubectl karmadactl helm git go; do
  printf "%-10s " "$t"
  if command -v "$t" >/dev/null 2>&1; then echo "present ($($t version 2>/dev/null | head -1 | cut -c1-40))"; else echo MISSING; fi
done
echo "=== docker access ==="
if docker ps >/dev/null 2>&1; then echo "docker: ok (no sudo)"; elif sudo docker ps >/dev/null 2>&1; then echo "docker: needs sudo (add user to docker group)"; else echo "docker: NOT installed/running"; fi
echo "=== disk ==="
df -h / | sed -n '1,2p'
