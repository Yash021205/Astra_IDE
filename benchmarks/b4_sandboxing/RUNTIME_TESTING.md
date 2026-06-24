# B4 — Testing the real sandbox runtimes (runc / gVisor / Firecracker)

The risk scorer (Paper 2) chooses a **tier**; `sandbox_runtime.build_workspace_pod_manifest()`
turns that tier into a Pod with `runtimeClassName: runc|gvisor|firecracker` plus
defence-in-depth hardening. This document is how you **empirically validate the
runtimes themselves** — the overhead/isolation trade-off that justifies adaptive
tiering (docs/research/01-adaptive-sandboxing.md §1.1).

> **Why this is a separate runbook:** runc/gVisor/Firecracker are Linux-kernel
> features. They cannot run on the Windows dev box — run everything below on the
> **GCP e2-standard-4 Linux node** (nested-virt enabled for Firecracker). The
> manifest builder + tier logic are unit-tested cross-platform; this validates
> the runtimes under them.

There are **two** things to measure, and they are the whole point of B4:

1. **Overhead** — startup latency + syscall/IO cost per tier (the *price* of isolation).
2. **Isolation** — does each tier actually *block* the escape vectors (the *benefit*).

---

## 1. Install the three runtimes (one-time, on the node)

```bash
# --- runc: already the default containerd/Docker runtime, nothing to install ---

# --- gVisor (runsc) ---
( set -e
  ARCH=$(uname -m)
  URL=https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}
  wget -q ${URL}/runsc ${URL}/containerd-shim-runsc-v1
  chmod +x runsc containerd-shim-runsc-v1 && sudo mv runsc containerd-shim-runsc-v1 /usr/local/bin/ )
# register the runsc runtime with containerd, then restart it:
sudo runsc install && sudo systemctl restart containerd

# --- Firecracker via Kata Containers (kata-fc handler) ---
# Kata provides the k8s RuntimeClass that boots a Firecracker microVM per pod.
sudo snap install kata-containers --classic   # or the kata-deploy DaemonSet on k8s
# requires /dev/kvm (nested virtualization) on the node:
ls -l /dev/kvm    # must exist; on GCP enable "nested virtualization" on the VM
```

Register the RuntimeClasses (already defined in the repo):
```bash
kubectl apply -f k8s/base/runtime-classes.yaml
# label the node so gvisor/firecracker pods schedule onto it:
kubectl label node <NODE> sandbox.astra-ide.io/gvisor=true sandbox.astra-ide.io/firecracker=true
```
Smoke-check each handler is live:
```bash
for rc in runc gvisor firecracker; do
  kubectl run probe-$rc --rm -it --restart=Never \
    --overrides="{\"spec\":{\"runtimeClassName\":\"$rc\"}}" \
    --image=busybox -- sh -c 'uname -a; id'
done
```
A telltale: under **gVisor**, `uname -r` reports a gVisor version string, and
`dmesg` is empty — you are talking to the Sentry user-space kernel, not the host.

---

## 2. Overhead benchmark → reproduce the §1.1 numbers

Run `runtime_bench.sh` on the node. For each runtime it measures (a) container
**startup latency** to first user instruction, (b) a **syscall-heavy** microbench
(tight `stat()`/`getpid()` loop), and (c) **CPU** (sysbench). It prints a table to
compare against the published figures we cite:

```bash
bash benchmarks/b4_sandboxing/runtime_bench.sh | tee benchmarks/b4_sandboxing/results/runtime_overhead.txt
```

Expected shape (from the literature — your numbers should land in these bands):

| Runtime | Startup | CPU vs bare-metal | Syscall-heavy | Source to match |
|---|---|---|---|---|
| runc | 50–100 ms | ~100% (baseline) | baseline | baseline |
| gVisor | 50–150 ms | ~near-native | **+10–40%** (median ~18%) | gVisor perf guide; Ant 2021 |
| Firecracker (Kata) | **<125 ms** to app | **>95%** | low CPU, higher I/O | Agache NSDI 2020 |

If your gVisor syscall overhead lands ~15–25% and Firecracker boots <125 ms with
CPU >95%, you have **reproduced the trade-off** that the adaptive scorer exploits.

---

## 3. Isolation benchmark → does each tier block the escapes?

This is the *benefit* side and ties directly to **Paper 2 (SandboxEscapeBench)**.
Run a representative escape primitive **inside** a pod of each runtime and record
whether it succeeds. Use only safe, observable probes (no real host damage):

| Probe (escape vector) | runc (shared kernel) | gVisor | Firecracker |
|---|---|---|---|
| read host kernel via `/proc/1/...`, `dmesg` | often visible | blocked (own kernel) | blocked (microVM) |
| `mount -t cgroup ... release_agent` (CVE-2022-0492) | may succeed w/o seccomp | blocked | blocked |
| `unshare --map-root-user` namespace (CVE-2022-0185) | kernel-dependent | blocked | blocked |
| load kernel module `insmod` | denied by caps | N/A (no host kernel) | N/A |

```bash
# example probe under each runtime (observe, don't damage):
for rc in runc gvisor firecracker; do
  echo "== $rc =="
  kubectl run esc-$rc --rm -it --restart=Never \
    --overrides="{\"spec\":{\"runtimeClassName\":\"$rc\"}}" --image=alpine -- \
    sh -c 'cat /proc/1/status | head -1; unshare --map-root-user --user echo NS_OK 2>&1 | tail -1'
done
```
The story for the panel: **the same escape probe that surfaces host state under
runc is contained under gVisor/Firecracker** — which is exactly why the scorer
routes high-risk (untrusted, shell, network) workloads to the stronger tier, and
keeps low-risk ones on fast runc.

---

## 4. The graph that makes B4's case

Plot **overhead (x)** vs **escape-block-rate (y)** for the three runtimes from §2
and §3. runc sits bottom-left (cheap, weak), Firecracker top-right (costly,
strong), gVisor in between. Overlay the scorer's thresholds (0.30, 0.70): this
single figure shows ASTRA spends isolation budget *only* where risk demands it —
the core B4 claim, now backed by your own measurements next to the published
ones.

Truly automated escape PoCs (the 18 SandboxEscapeBench scenarios) require their
agent harness; for the BTP, the probe table above + the overhead reproduction is
a defensible, panel-grade validation without that infrastructure.
