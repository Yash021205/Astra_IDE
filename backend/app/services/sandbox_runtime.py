"""
Sandbox tier ENFORCEMENT — turn a chosen tier (runc / gvisor / firecracker) into
the Kubernetes Pod spec that actually runs the workload under that runtime.

This closes the gap flagged in docs/research/01-adaptive-sandboxing.md §4
("Tier → pod: mocked field → maps to real K8s RuntimeClass, launches pod"):
- `build_workspace_pod_manifest()` is a PURE function (no cluster calls), so it
  is unit-tested on any OS. It sets `spec.runtimeClassName` to the tier and adds
  defence-in-depth hardening (drop all caps, no-new-privileges, seccomp
  RuntimeDefault, non-root, read-only rootfs when the workload doesn't need
  writes) on top of whatever isolation the runtime itself provides.
- Actually submitting the manifest needs a live cluster with the RuntimeClasses
  installed (runsc for gvisor, Kata/Firecracker for firecracker). That step and
  the overhead/isolation benchmark are documented in
  benchmarks/b4_sandboxing/RUNTIME_TESTING.md and run on the Linux node.

RuntimeClass handlers mirror k8s/base/runtime-classes.yaml.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# tier -> (RuntimeClass name, container-runtime handler, node label gate)
RUNTIME_HANDLERS: dict[str, dict[str, Optional[str]]] = {
    "runc":        {"handler": "runc",    "node_label": None},
    "gvisor":      {"handler": "runsc",   "node_label": "sandbox.astra-ide.io/gvisor"},
    "firecracker": {"handler": "kata-fc", "node_label": "sandbox.astra-ide.io/firecracker"},
}

NAMESPACE = "astra-ide"


def runtime_class_for_tier(tier: str) -> str:
    if tier not in RUNTIME_HANDLERS:
        raise ValueError(f"unknown sandbox tier {tier!r}; expected one of "
                         f"{sorted(RUNTIME_HANDLERS)}")
    return tier


def _security_context(filesystem_write: bool) -> dict:
    """
    Defence-in-depth applied at every tier (the runtime adds its own isolation
    on top). Grounded in the escape-vector taxonomy in
    docs/research/01-adaptive-sandboxing.md §2.5 — drop the capabilities and
    privilege-escalation paths that container breakouts rely on.
    """
    return {
        "runAsNonRoot": True,
        "runAsUser": 1000,
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": not filesystem_write,
        "privileged": False,
        "capabilities": {"drop": ["ALL"]},
        "seccompProfile": {"type": "RuntimeDefault"},
    }


def build_workspace_pod_manifest(
    *,
    workspace_id: int,
    user_id: int,
    language: str,
    tier: str,
    pod_name: str,
    node_name: str = "",
    cpu_request: float = 0.5,
    memory_request: int = 512,
    network_access: bool = False,
    filesystem_write: bool = True,
    image: str = "codercom/code-server:latest",
) -> dict:
    """Build the full Pod manifest that runs this workspace under `tier`."""
    rc = runtime_class_for_tier(tier)
    gate = RUNTIME_HANDLERS[tier]["node_label"]

    manifest: dict = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": NAMESPACE,
            "labels": {
                "app": "astra-workspace",
                "workspace-id": str(workspace_id),
                "user-id": str(user_id),
                "language": language,
                "sandbox-tier": tier,
            },
        },
        "spec": {
            "runtimeClassName": rc,                 # <- the enforced isolation tier
            "restartPolicy": "Never",
            "automountServiceAccountToken": False,  # no API creds inside untrusted pod
            "securityContext": {
                "runAsNonRoot": True,
                "seccompProfile": {"type": "RuntimeDefault"},
            },
            "containers": [{
                "name": "ide",
                "image": image,
                "securityContext": _security_context(filesystem_write),
                "resources": {
                    "requests": {"cpu": str(cpu_request),
                                 "memory": f"{memory_request}Mi"},
                    "limits": {"cpu": str(cpu_request * 2),
                               "memory": f"{memory_request * 2}Mi"},
                },
                "env": [
                    {"name": "WORKSPACE_ID", "value": str(workspace_id)},
                    {"name": "USER_ID", "value": str(user_id)},
                ],
            }],
        },
    }

    # gVisor / Firecracker run only on nodes labelled for that runtime.
    if gate:
        manifest["spec"]["nodeSelector"] = {gate: "true"}
    if node_name:
        manifest["spec"].setdefault("nodeSelector", {})  # keep label gate too
        manifest["spec"]["nodeName"] = node_name

    # No egress for untrusted workloads unless explicitly granted (a NetworkPolicy
    # enforces this; the label is the selector the policy matches).
    manifest["metadata"]["labels"]["egress"] = "allow" if network_access else "deny"
    return manifest


def manifest_for_workspace(ws) -> dict:
    """Convenience adapter from an ORM Workspace object."""
    return build_workspace_pod_manifest(
        workspace_id=ws.id, user_id=ws.owner_id, language=ws.language,
        tier=ws.sandbox_tier, pod_name=ws.pod_name, node_name=ws.node_name,
        cpu_request=ws.cpu_request, memory_request=ws.memory_request,
        network_access=ws.network_access, filesystem_write=ws.filesystem_write,
    )


# ── Applying the manifest (the actual launch) ──────────────────────────────────

def to_yaml(manifest: dict) -> str:
    """Render the manifest for `kubectl apply -f -` (the manual / GCP-node path)."""
    import yaml
    return yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False)


@dataclass
class LaunchResult:
    applied:       bool
    pod_name:      str
    runtime_class: str
    reason:        str
    manifest_yaml: str


def apply_workspace_pod(ws, *, dry_run: Optional[bool] = None) -> LaunchResult:
    """
    Submit the workspace's enforcement manifest to Kubernetes.

    Safe by default: it is a DRY-RUN (no cluster call) unless
    `ASTRA_K8S_APPLY=1` is set AND the kubernetes client + a reachable cluster
    exist. Without a cluster it returns the rendered YAML so the pod can be
    applied by hand on the GCP node (see benchmarks/b4_sandboxing/RUNTIME_TESTING.md).
    This keeps the enforcement path fully exercised in dev (Windows) while the
    real gVisor/Firecracker launch happens on the Linux cluster.
    """
    manifest = manifest_for_workspace(ws)
    y = to_yaml(manifest)
    rc = manifest["spec"]["runtimeClassName"]
    pod = manifest["metadata"]["name"]

    if dry_run is None:
        dry_run = os.getenv("ASTRA_K8S_APPLY") != "1"
    if dry_run:
        return LaunchResult(False, pod, rc,
                            "dry-run (set ASTRA_K8S_APPLY=1 on a cluster to apply)", y)

    try:
        from kubernetes import client, config  # optional dependency
    except ImportError:
        return LaunchResult(False, pod, rc,
                            "kubernetes client not installed; apply YAML manually", y)
    try:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        client.CoreV1Api().create_namespaced_pod(
            namespace=manifest["metadata"]["namespace"], body=manifest)
        return LaunchResult(True, pod, rc, "applied", y)
    except Exception as e:                       # cluster unreachable / RBAC / dup
        return LaunchResult(False, pod, rc, f"apply failed: {type(e).__name__}: {e}", y)
