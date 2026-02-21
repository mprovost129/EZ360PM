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
    def __init__(self, *args, **kwargs):
        if getattr(settings, "USE_S3", False) and _S3Boto3Storage is not None:
            kwargs.setdefault(
                "bucket_name",
                getattr(settings, "S3_PUBLIC_MEDIA_BUCKET", "") or getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""),
            )
            kwargs.setdefault("location", getattr(settings, "S3_PUBLIC_MEDIA_LOCATION", "public-media"))

            # Bucket has ACLs disabled -> do not send ACL headers
            kwargs.setdefault("default_acl", None)

            # If you truly want "public-ish", that must be done via bucket policy / CloudFront,
            # not ACLs.
            kwargs.setdefault("querystring_auth", False)
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
            kwargs.setdefault(
                "bucket_name",
                getattr(settings, "S3_PRIVATE_MEDIA_BUCKET", "") or getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""),
            )
            kwargs.setdefault("location", getattr(settings, "S3_PRIVATE_MEDIA_LOCATION", "private-media"))
        
            # IMPORTANT: Bucket has ACLs disabled (Object Ownership: Bucket owner enforced).
            # Do not set any ACL headers.
            kwargs.setdefault("default_acl", None)
        
            # Private objects served via signed URLs.
            kwargs.setdefault("querystring_auth", True)
            kwargs.setdefault("querystring_expire", int(getattr(settings, "S3_PRIVATE_MEDIA_EXPIRE_SECONDS", 600)))
        super().__init__(*args, **kwargs)
