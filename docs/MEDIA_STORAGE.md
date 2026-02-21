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

If you only want one bucket, you can leave the S3_*_BUCKET vars blank and set `AWS_STORAGE_BUCKET_NAME`.

## Direct-to-S3 uploads (presigned POST)

When enabled, large uploads do **not** flow through your Django server.

Enable:
- `USE_S3=1`
- `S3_DIRECT_UPLOADS=1`

Tuning:
- `S3_PRESIGN_MAX_SIZE_MB` (default 25)
- `S3_PRESIGN_EXPIRE_SECONDS` (default 300)

How it works:
- The browser requests a presigned POST policy from `/api/v1/storage/presign/` (Manager+ only).
- The browser uploads directly to the private S3 bucket.
- The app stores the resulting object key on the model.

### AWS CORS example (private bucket)

Add a CORS rule to the **private** media bucket to allow browser uploads:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["POST"],
    "AllowedOrigins": ["http://127.0.0.1:8000", "http://localhost:8000", "https://YOURDOMAIN"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

If you upload from additional origins (staging, alternate domains), add them to `AllowedOrigins`.
