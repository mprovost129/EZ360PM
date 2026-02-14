from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

try:
    from storages.backends.s3boto3 import S3Boto3Storage as _S3Boto3Storage  # type: ignore
except Exception:  # pragma: no cover
    _S3Boto3Storage = None  # type: ignore


_BaseStorage = _S3Boto3Storage or FileSystemStorage


@deconstructible
class PublicMediaStorage(_BaseStorage):
    """Public-ish media storage.

    - If USE_S3=1 and django-storages is installed: uses S3_PUBLIC_MEDIA_BUCKET (or AWS_STORAGE_BUCKET_NAME)
      with S3_PUBLIC_MEDIA_LOCATION.
    - Else: falls back to local FileSystemStorage (MEDIA_ROOT).
    """

    def __init__(self, *args, **kwargs):
        if getattr(settings, "USE_S3", False) and _S3Boto3Storage is not None:
            kwargs.setdefault("bucket_name", getattr(settings, "S3_PUBLIC_MEDIA_BUCKET", "") or getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""))
            kwargs.setdefault("location", getattr(settings, "S3_PUBLIC_MEDIA_LOCATION", "public-media"))
            kwargs.setdefault("default_acl", None)
        super().__init__(*args, **kwargs)


@deconstructible
class PrivateMediaStorage(_BaseStorage):
    """Private media storage (receipts, project files).

    - If USE_S3=1 and django-storages is installed: uses S3_PRIVATE_MEDIA_BUCKET (or AWS_STORAGE_BUCKET_NAME)
      with S3_PRIVATE_MEDIA_LOCATION and private ACL.
    - Else: falls back to local FileSystemStorage (MEDIA_ROOT).
    """

    def __init__(self, *args, **kwargs):
        if getattr(settings, "USE_S3", False) and _S3Boto3Storage is not None:
            kwargs.setdefault("bucket_name", getattr(settings, "S3_PRIVATE_MEDIA_BUCKET", "") or getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""))
            kwargs.setdefault("location", getattr(settings, "S3_PRIVATE_MEDIA_LOCATION", "private-media"))
            kwargs.setdefault("default_acl", None)
            # IMPORTANT: private objects must be served via signed URLs.
            # django-storages generates presigned URLs when querystring_auth=True.
            kwargs.setdefault("querystring_auth", True)
            kwargs.setdefault("querystring_expire", int(getattr(settings, "S3_PRIVATE_MEDIA_EXPIRE_SECONDS", 600)))
        super().__init__(*args, **kwargs)
