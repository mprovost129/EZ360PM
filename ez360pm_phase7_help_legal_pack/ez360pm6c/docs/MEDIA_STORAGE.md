# Media Storage (Uploads)

Default behavior:
- Uploaded files are stored on the local filesystem at `MEDIA_ROOT`, served at `MEDIA_URL`.

## Option: S3 / S3-compatible storage

This project supports S3-based media storage via **django-storages**.

1) Install dependency:
- `pip install "django-storages[boto3]"`

2) Set env vars:
- `USE_S3=1`
- `AWS_ACCESS_KEY_ID=...`
- `AWS_SECRET_ACCESS_KEY=...`
- `AWS_STORAGE_BUCKET_NAME=...`
- `AWS_S3_REGION_NAME=...`
- Optional:
  - `AWS_S3_ENDPOINT_URL=...` (MinIO / DigitalOcean Spaces / etc.)
  - `AWS_S3_CUSTOM_DOMAIN=media.yourdomain.com` (recommended)

3) Verify:
- Upload a receipt or document attachment in the app.
- Confirm the stored file URL resolves and loads.

Notes:
- Static files are still served via `collectstatic` (filesystem) by default.
- Media URLs will use `AWS_S3_CUSTOM_DOMAIN` when provided.



## Multiple buckets (recommended)

Set these env vars:

- `USE_S3=1`
- `S3_PUBLIC_MEDIA_BUCKET` (company logos / general media)
- `S3_PRIVATE_MEDIA_BUCKET` (receipts / project files)

Optionally set locations (prefixes):

- `S3_PUBLIC_MEDIA_LOCATION=public-media`
- `S3_PRIVATE_MEDIA_LOCATION=private-media`

Private file access:
- Receipts and project files are stored in the **private bucket** and are accessed through app routes that enforce permissions.
- The private storage backend generates **presigned URLs** for downloads.
- Configure the presigned URL lifetime via:
  - `S3_PRIVATE_MEDIA_EXPIRE_SECONDS` (default `600`)


## Direct-to-S3 uploads (recommended)

For large uploads (receipts, project files), EZ360PM can upload **directly from the browser to S3** using a short-lived **presigned POST** generated server-side.

Env:
- `S3_PRESIGN_POST_EXPIRE_SECONDS` (default `300`)

AWS bucket CORS (example)

Add a CORS rule on the *private media bucket* that allows browser POST uploads from your app origin:

```json
[
  {
    "AllowedOrigins": ["https://YOUR-APP-DOMAIN"],
    "AllowedMethods": ["POST"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

Notes:
- Keep origins tight (only your production/staging domains).
- Private bucket should still have **Block Public Access** enabled.

Lifecycle rules (recommended)
- At minimum, configure **AbortIncompleteMultipartUpload** (e.g., 7 days).
- Optional: expire Ops smoke-test objects under `private-media/ops/smoke/` after 30 days.

If you only want one bucket, you can leave the S3_*_BUCKET vars blank and set `AWS_STORAGE_BUCKET_NAME`.


## Ops verification
- Use **Ops → Storage** to:
  - Confirm bucket names/locations and presign expiry values.
  - Run the storage smoke tests (tiny upload + signed URL generation).
- Use **Ops → Storage → Production readiness** to record manual AWS console posture checks:
  - Block Public Access ON (private bucket)
  - CORS configured for presigned POST
  - Lifecycle rules configured
  - E2E receipts + E2E project files verified
- For staging/prod verification, also test end-to-end flows in the UI:
  - Expense receipt upload + secure download
  - Project file upload + secure download

## ACL posture
- Preferred posture: **no object ACLs** (`AWS_DEFAULT_ACL=None`, storages `default_acl=None`).
- Enforce access via:
  - Bucket policy (public media if needed)
  - Block Public Access (private bucket)
  - Signed URLs for private objects.
