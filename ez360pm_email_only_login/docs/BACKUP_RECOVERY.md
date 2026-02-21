# EZ360PM — Backup & Recovery (Phase 3G)

This pack adds a first-class backup command:

- `python manage.py ez360_backup` (PostgreSQL dump via `pg_dump`)
- optional: `python manage.py ez360_backup --media` (tar.gz of `MEDIA_ROOT`)
- retention pruning (keep-last + max-age)

> Goal: you can **restore** your production database and validate the restore procedure on a schedule.

---

## 1) Requirements

### PostgreSQL client tools
The backup command requires `pg_dump` to exist on the host PATH.

- Linux: install `postgresql-client` (package name varies by distro)
- Windows dev: install Postgres (includes `pg_dump`), or add its `bin/` to PATH.

If you are using a managed platform that does not provide `pg_dump`, use:
- provider-managed DB backups (recommended), **or**
- a sidecar job/container that includes the Postgres client tools.

---

## 2) Configuration (env vars)

These are read by `config/settings/base.py`:

- `EZ360_BACKUP_DIR` (default: `<BASE_DIR>/backups`)
- `EZ360_BACKUP_RETENTION_DAYS` (default: 14)
- `EZ360_BACKUP_KEEP_LAST` (default: 14)

For production, set `EZ360_BACKUP_DIR` to a **persistent volume** path.

---

## 3) Run a backup

### DB backup (default)
```bash
python manage.py ez360_backup
```

### DB + Media backup
```bash
python manage.py ez360_backup --db --media
```

### Override output directory
```bash
python manage.py ez360_backup --out-dir /var/backups/ez360pm
```

---

## 4) Restore procedure (manual, explicit)

**Recommended:** restore to a **fresh** empty DB (or staging DB) first.

### Custom-format dump (.dump)
Example:
```bash
# environment:
# POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

pg_restore -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
  --clean --if-exists \
  -d "$POSTGRES_DB" \
  /path/to/ez360pm_db_YYYYMMDD_HHMMSS_utc.dump
```

Then run:
```bash
python manage.py migrate
python manage.py check
```

---

## 5) Restore test (acceptance)

At least monthly (weekly is better during launch), do:

1. Create a fresh staging DB.
2. Restore the newest backup dump into it.
3. Run `python manage.py migrate` and smoke tests:
   - login
   - company switch
   - create client/project
   - create invoice
   - run reports (P&L / Balance Sheet)
4. Document the test date and outcome in `docs/MEMORY.md`.

---

## 6) Scheduling (cron example)

Daily at 2:15 AM:
```cron
15 2 * * * /path/to/venv/bin/python /srv/ez360pm/manage.py ez360_backup >> /var/log/ez360pm_backup.log 2>&1
```

---

## Notes on media strategy

For a truly professional app, media should live in object storage (S3-compatible) with:
- bucket versioning (optional)
- lifecycle rules (retention)
- server-side encryption
- least-privilege credentials

The `--media` tarball is meant for single-server deployments and emergency portability.
