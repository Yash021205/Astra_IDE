#!/usr/bin/env bash
# Installs Kata Containers with the Firecracker hypervisor and wires it into k3s
# as the `kata-fc` runtime handler, which the existing `firecracker` RuntimeClass
# already points at.
set -euxo pipefail

# Kata 4.x publishes the bundle as .tar.zst, so zstd must be present.
command -v zstd >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq zstd)

# ── 1. Kata static bundle. Write the release JSON to a file first: piping curl
#      into grep -m1 closes the pipe early and makes curl fail under pipefail.
curl -fsSL -o /tmp/kata-release.json \
  https://api.github.com/repos/kata-containers/kata-containers/releases/latest
TAG=$(sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' /tmp/kata-release.json | head -1)
VER=${TAG#v}
echo "kata release: ${TAG} (version ${VER})"

if [ ! -x /opt/kata/bin/containerd-shim-kata-v2 ]; then
  curl -fSL --retry 3 -o /tmp/kata.tar.zst \
    "https://github.com/kata-containers/kata-containers/releases/download/${TAG}/kata-static-${VER}-amd64.tar.zst"
  ls -la /tmp/kata.tar.zst
  # The tarball is rooted at ./opt/kata/...
  tar --zstd -xf /tmp/kata.tar.zst -C /
  rm -f /tmp/kata.tar.zst
fi

# ── 2. Shim symlinks. containerd resolves runtime_type "io.containerd.kata-fc.v2"
#      to the binary containerd-shim-kata-fc-v2; Kata picks configuration-fc.toml
#      from the "-fc" suffix in that name.
ln -sf /opt/kata/bin/containerd-shim-kata-v2 /usr/local/bin/containerd-shim-kata-v2
ln -sf /opt/kata/bin/containerd-shim-kata-v2 /usr/local/bin/containerd-shim-kata-fc-v2
ln -sf /opt/kata/bin/kata-runtime            /usr/local/bin/kata-runtime

# ── 3. Firecracker binary: prefer the one Kata ships, else fetch upstream.
if [ ! -x /opt/kata/bin/firecracker ]; then
  curl -fsSL -o /tmp/fc-release.json \
    https://api.github.com/repos/firecracker-microvm/firecracker/releases/latest
  FC_TAG=$(sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' /tmp/fc-release.json | head -1)
  curl -fSL --retry 3 -o /tmp/fc.tgz \
    "https://github.com/firecracker-microvm/firecracker/releases/download/${FC_TAG}/firecracker-${FC_TAG}-x86_64.tgz"
  tar -xzf /tmp/fc.tgz -C /tmp
  install -m755 "/tmp/release-${FC_TAG}-x86_64/firecracker-${FC_TAG}-x86_64" /opt/kata/bin/firecracker
  install -m755 "/tmp/release-${FC_TAG}-x86_64/jailer-${FC_TAG}-x86_64"      /opt/kata/bin/jailer || true
fi

echo "--- versions ---"
/opt/kata/bin/firecracker --version 2>&1 | head -2 || true

echo "--- fc config present? ---"
ls -la /opt/kata/share/defaults/kata-containers/configuration-fc.toml

# ── 4. Register kata-fc with k3s containerd, on the devmapper snapshotter.
cat > /var/lib/rancher/k3s/agent/etc/containerd/config-v3.toml.d/kata-fc.toml <<'EOF'
version = 3

[plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.kata-fc]
  runtime_type = 'io.containerd.kata-fc.v2'
  # Firecracker has no virtio-fs, so each container needs a block device.
  snapshotter = 'devmapper'
  privileged_without_host_devices = true
EOF

systemctl restart k3s
sleep 25
echo "SETUP_KATA_FC_DONE"
