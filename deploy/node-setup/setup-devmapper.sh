#!/usr/bin/env bash
# Sets up a devmapper thin-pool for containerd.
#
# Firecracker has no virtio-fs, so Kata's firecracker hypervisor cannot share a
# rootfs via overlayfs the way runc/gVisor do -- it needs a block device per
# container. containerd's devmapper snapshotter provides that. The pool is backed
# by loop devices over sparse files, which do not survive a reboot, so a systemd
# unit recreates it on every boot before k3s starts.
set -euo pipefail

DATA_DIR=/var/lib/containerd/devmapper
POOL_NAME=containerd-pool
DATA_SIZE=40G
META_SIZE=4G

mkdir -p "${DATA_DIR}"

# Idempotent: if the pool is already active, nothing to do.
if dmsetup info "${POOL_NAME}" >/dev/null 2>&1; then
  echo "thin-pool ${POOL_NAME} already active"
  exit 0
fi

[ -f "${DATA_DIR}/data" ] || truncate -s "${DATA_SIZE}" "${DATA_DIR}/data"
[ -f "${DATA_DIR}/meta" ] || truncate -s "${META_SIZE}" "${DATA_DIR}/meta"

# Reuse an existing loop binding if the file is already attached.
DATA_DEV=$(losetup -j "${DATA_DIR}/data" | cut -d: -f1)
[ -z "${DATA_DEV}" ] && DATA_DEV=$(losetup --find --show "${DATA_DIR}/data")
META_DEV=$(losetup -j "${DATA_DIR}/meta" | cut -d: -f1)
[ -z "${META_DEV}" ] && META_DEV=$(losetup --find --show "${DATA_DIR}/meta")

SECTOR_SIZE=512
DATA_BYTES=$(blockdev --getsize64 -q "${DATA_DEV}")
LENGTH_SECTORS=$(( DATA_BYTES / SECTOR_SIZE ))
DATA_BLOCK_SIZE=128        # 64KB, containerd's documented default
LOW_WATER_MARK=32768

dmsetup create "${POOL_NAME}" \
  --table "0 ${LENGTH_SECTORS} thin-pool ${META_DEV} ${DATA_DEV} ${DATA_BLOCK_SIZE} ${LOW_WATER_MARK}"

echo "created thin-pool ${POOL_NAME} (data=${DATA_DEV} meta=${META_DEV})"
dmsetup status "${POOL_NAME}"
