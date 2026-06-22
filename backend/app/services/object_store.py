"""
Object storage (tech-stack §9: "Object Storage: MinIO — S3-compatible").

Workspace snapshots: tar.gz a workspace's file tree and store it as an object,
restore it on demand. Uses the S3-compatible MinIO client; if the server is
unreachable the calls return a clear "unavailable" result instead of raising,
so the rest of the app keeps working without object storage in dev.
"""
from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from app.core.config import get_settings
from app.services import workspace_files

settings = get_settings()
_BUCKET = "astra-workspaces"


@dataclass
class StoreResult:
    ok: bool
    detail: str
    key: str = ""
    size: int = 0


def _client():
    """Build a MinIO client, or None if the package/endpoint is unavailable."""
    try:
        import urllib3
        from minio import Minio
        ep = urlparse(settings.minio_endpoint)
        secure = ep.scheme == "https"
        host = ep.netloc or ep.path           # "http://host:9000" -> "host:9000"
        # Bound the probe: fail fast (no long retries) when MinIO isn't running.
        http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=0.5, read=1.0),
                                   retries=urllib3.Retry(total=0))
        client = Minio(host, access_key=settings.minio_access_key,
                       secret_key=settings.minio_secret_key, secure=secure,
                       http_client=http)
        # cheap reachability probe (also surfaces auth errors early)
        client.bucket_exists(_BUCKET)
        return client
    except Exception:
        return None


def is_available() -> bool:
    return _client() is not None


def _ensure_bucket(client) -> None:
    if not client.bucket_exists(_BUCKET):
        client.make_bucket(_BUCKET)


def snapshot_workspace(workspace_id: int) -> StoreResult:
    """tar.gz the workspace dir and upload it as <id>/snapshot.tar.gz."""
    client = _client()
    if client is None:
        return StoreResult(False, "object storage (MinIO) unavailable")
    base = workspace_files.workspace_dir(workspace_id)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(base), arcname=".")
    data = buf.getvalue()
    key = f"{workspace_id}/snapshot.tar.gz"
    try:
        _ensure_bucket(client)
        client.put_object(_BUCKET, key, io.BytesIO(data), length=len(data),
                          content_type="application/gzip")
        return StoreResult(True, "snapshot stored", key, len(data))
    except Exception as e:
        return StoreResult(False, f"upload failed: {e}")


def restore_workspace(workspace_id: int) -> StoreResult:
    """Download and extract the latest snapshot back into the workspace dir."""
    client = _client()
    if client is None:
        return StoreResult(False, "object storage (MinIO) unavailable")
    key = f"{workspace_id}/snapshot.tar.gz"
    base = workspace_files.workspace_dir(workspace_id)
    try:
        resp = client.get_object(_BUCKET, key)
        data = resp.read()
        resp.close(); resp.release_conn()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            tar.extractall(str(base))        # paths are workspace-relative (arcname=".")
        return StoreResult(True, "snapshot restored", key, len(data))
    except Exception as e:
        return StoreResult(False, f"restore failed: {e}")
