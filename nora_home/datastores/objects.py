"""
Object storage — photos, exports, backups, robot recordings.

In production this is MinIO on the Pi (S3-compatible, runs in a container). With
NORA_HOME_S3_ENABLED=0 everything falls back to MEDIA_ROOT on local disk, so laptop
development needs no infrastructure.

House apps normally just use a Django FileField — `default_storage` is already
pointed at the right place. Reach for this module when you need presigned URLs,
raw bytes, or a key outside the media namespace (backups, for example).

    from nora_home.datastores.objects import put_bytes, presigned_url

    key = put_bytes("workout/form-check.mp4", data, app_slug="workout")
    url = presigned_url(key, expires=900)
"""

from __future__ import annotations

import io
import logging
import threading

from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

_s3 = None
_lock = threading.Lock()


class StorageUnavailable(Exception):
    pass


def _client():
    global _s3
    if not settings.NORA_HOME_S3_ENABLED:
        raise StorageUnavailable("Object storage is disabled (NORA_HOME_S3_ENABLED=0).")
    if _s3 is None:
        with _lock:
            if _s3 is None:
                try:
                    import boto3
                    from botocore.config import Config
                except ImportError as exc:
                    raise StorageUnavailable("boto3 is not installed.") from exc
                _s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.NORA_HOME_S3_ENDPOINT_URL,
                    aws_access_key_id=settings.NORA_HOME_S3_ACCESS_KEY,
                    aws_secret_access_key=settings.NORA_HOME_S3_SECRET_KEY,
                    region_name=settings.NORA_HOME_S3_REGION,
                    use_ssl=settings.NORA_HOME_S3_USE_SSL,
                    config=Config(signature_version="s3v4",
                                  s3={"addressing_style": "path"}),
                )
    return _s3


def namespaced(key: str, app_slug: str = "core") -> str:
    return f"{app_slug}/{key.lstrip('/')}"


def put_bytes(key: str, data: bytes, *, app_slug: str = "core",
              content_type: str = "application/octet-stream") -> str:
    """Store bytes and return the key they live under."""
    full_key = namespaced(key, app_slug)
    if not settings.NORA_HOME_S3_ENABLED:
        default_storage.save(full_key, io.BytesIO(data))
        return full_key
    _client().put_object(Bucket=settings.NORA_HOME_S3_BUCKET, Key=full_key, Body=data,
                         ContentType=content_type)
    return full_key


def get_bytes(key: str) -> bytes:
    if not settings.NORA_HOME_S3_ENABLED:
        with default_storage.open(key, "rb") as handle:
            return handle.read()
    response = _client().get_object(Bucket=settings.NORA_HOME_S3_BUCKET, Key=key)
    return response["Body"].read()


def put_file(key: str, path, *, app_slug: str = "core") -> str:
    """Upload a file from disk — used by the backup command for large dumps."""
    full_key = namespaced(key, app_slug)
    if not settings.NORA_HOME_S3_ENABLED:
        with open(path, "rb") as handle:
            default_storage.save(full_key, handle)
        return full_key
    _client().upload_file(str(path), settings.NORA_HOME_S3_BUCKET, full_key)
    return full_key


def presigned_url(key: str, expires: int = 3600) -> str:
    """A time-limited link — the right way to show a photo to a phone browser
    without making the bucket public."""
    if not settings.NORA_HOME_S3_ENABLED:
        return default_storage.url(key)
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.NORA_HOME_S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def delete(key: str):
    if not settings.NORA_HOME_S3_ENABLED:
        default_storage.delete(key)
        return
    _client().delete_object(Bucket=settings.NORA_HOME_S3_BUCKET, Key=key)


def ensure_bucket() -> bool | None:
    """Create the bucket on first run so a fresh Pi needs no manual MinIO setup.

    True if it was created, False if it already existed, None if object storage is
    switched off — the caller needs to tell those three apart.
    """
    if not settings.NORA_HOME_S3_ENABLED:
        return None
    client = _client()
    try:
        client.head_bucket(Bucket=settings.NORA_HOME_S3_BUCKET)
        return False
    except Exception:
        client.create_bucket(Bucket=settings.NORA_HOME_S3_BUCKET)
        logger.info("Created object storage bucket %s", settings.NORA_HOME_S3_BUCKET)
        return True
