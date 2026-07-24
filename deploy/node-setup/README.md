# Node setup: real sandbox runtimes on the k3s node

These scripts make all three isolation tiers genuinely real on the VM. They are
idempotent and safe to re-run.

| Tier | Runtime | Isolation |
|---|---|---|
| `runc` | runc | namespaces + cgroups (shared host kernel) |
| `gvisor` | runsc | user-space kernel intercepting syscalls |
| `firecracker` | kata-fc | hardware-virtualised micro-VM with its own kernel |

## Prerequisites

Firecracker needs KVM inside the guest, so the instance must support **nested
virtualisation**. E2 machine types cannot do this at all. The VM runs
`n2-standard-4` with nested virtualisation enabled:

```bash
gcloud compute instances stop astra-cluster-a --zone asia-south1-a
gcloud compute instances set-machine-type astra-cluster-a --zone asia-south1-a \
  --machine-type n2-standard-4
# gcloud's `instances update` has no --enable-nested-virtualization flag, and the
# Compute API does not expose PATCH on instances, so set it with a full PUT:
#   GET the instance JSON, add
#   advancedMachineFeatures.enableNestedVirtualization = true, then PUT it back to
#   .../instances/astra-cluster-a?most_disruptive_allowed_action=RESTART
gcloud compute instances start astra-cluster-a --zone asia-south1-a
```

Verify in the guest: `/dev/kvm` exists and
`cat /sys/module/kvm_intel/parameters/nested` prints `Y`.

## 1. `setup-devmapper.sh`

Creates a containerd devmapper thin-pool. Firecracker has no virtio-fs, so it
cannot share a rootfs over overlayfs the way runc and gVisor do — each container
needs a block device. Installed as a systemd unit that runs before k3s, because
the loop devices do not survive a reboot:

```bash
sudo install -m755 setup-devmapper.sh /usr/local/sbin/astra-devmapper.sh
sudo systemctl enable --now astra-devmapper.service
```

A k3s containerd drop-in registers the snapshotter at
`/var/lib/rancher/k3s/agent/etc/containerd/config-v3.toml.d/devmapper.toml`.

## 2. gVisor

```bash
ARCH=$(uname -m); URL=https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}
wget ${URL}/runsc ${URL}/containerd-shim-runsc-v1
sudo install -m755 -t /usr/local/bin runsc containerd-shim-runsc-v1
```

Drop-in `config-v3.toml.d/runsc.toml` registers `runtime_type =
"io.containerd.runsc.v1"` for the `runsc` handler.

## 3. `setup-kata-firecracker.sh`

Installs the Kata Containers static bundle (~1.8 GB, ships firecracker, the guest
kernel and rootfs), symlinks `containerd-shim-kata-fc-v2`, and registers the
`kata-fc` runtime on the devmapper snapshotter.

## 4. Node labels

The RuntimeClasses in `k8s/base/runtime-classes.yaml` carry a `nodeSelector`, so
a node must advertise the tiers it can actually run or pods stay `Pending`:

```bash
kubectl label node <node> sandbox.astra-ide.io/gvisor=true --overwrite
kubectl label node <node> sandbox.astra-ide.io/firecracker=true --overwrite
```

`cluster_state.refresh_from_kubernetes()` reads these labels, so the dashboard and
the scheduler only offer a tier the node can genuinely provide.

## Verifying each tier is real

```bash
# gVisor: dmesg inside the pod is the gVisor sentry, not the host kernel
kubectl run gv -n astra-ide --image=busybox:1.36 --restart=Never \
  --overrides='{"spec":{"runtimeClassName":"gvisor"}}' --command -- dmesg
# -> "Starting gVisor..."

# Firecracker: the guest kernel differs from the host kernel
uname -r                                   # host, e.g. 6.1.0-51-cloud-amd64
kubectl run fc -n astra-ide --image=busybox:1.36 --restart=Never \
  --overrides='{"spec":{"runtimeClassName":"firecracker"}}' --command -- uname -r
# -> e.g. 6.18.35  (a different kernel proves a real micro-VM)
```
