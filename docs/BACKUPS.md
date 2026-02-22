# Backups & Restore Tests (Ops)

EZ360PM provides two management commands to support backups and retention:

- `python manage.py ez360_backup_db [--gzip] [--storage host_managed|s3]`
- `python manage.py ez360_prune_backups [--dry-run] [--storage host_managed|s3]`

EZ360PM also records restore test evidence:

- `python manage.py ez360_record_restore_test --outcome pass|fail --notes "..." --backup-file "/path/to/backup.sql.gz"`

> Important: EZ360PM does not schedule jobs by itself. Use your host scheduler.

Pack 22 adds an executive-grade **Backup & Recovery Gate**:

- `python manage.py ez360_verify_backups` (daily verification + integrity check)
- `python manage.py ez360_restore_drill` (prints a restore drill checklist; optional evidence recording)

---

## Recommended schedules

### Daily backup (example)
Run once per day during low-traffic hours.

- Command:
  - `python manage.py ez360_backup_db --gzip --storage host_managed`
- Then prune:
  - `python manage.py ez360_prune_backups --storage host_managed`

If you want backups written to S3, set:

- `BACKUP_STORAGE=s3`
- `BACKUP_S3_BUCKET=...`
- `BACKUP_S3_PREFIX=ez360pm/backups/db`

Then run:

- `python manage.py ez360_backup_db --gzip --storage s3`
- `python manage.py ez360_prune_backups --storage s3`

Also verify daily:

- `python manage.py ez360_verify_backups`

### Weekly prune (optional)
If you prefer pruning weekly:

- `python manage.py ez360_prune_backups --retention-days 30`

---

## Linux cron example

Edit crontab:

- `crontab -e`

Example (daily backup at 2:15am, daily prune at 2:45am):

```
15 2 * * * cd /srv/ez360pm && /srv/ez360pm/.venv/bin/python manage.py ez360_backup_db --gzip >> /var/log/ez360pm_backup.log 2>&1
45 2 * * * cd /srv/ez360pm && /srv/ez360pm/.venv/bin/python manage.py ez360_prune_backups >> /var/log/ez360pm_backup.log 2>&1
55 2 * * * cd /srv/ez360pm && /srv/ez360pm/.venv/bin/python manage.py ez360_verify_backups >> /var/log/ez360pm_backup_verify.log 2>&1
```

---

## Windows Task Scheduler example

Create two tasks:

1) **EZ360PM Daily Backup**
- Program: `C:\path\to\python.exe`
- Arguments: `manage.py ez360_backup_db --gzip`
- Start in: `C:\path\to\your\project`

2) **EZ360PM Prune Backups**
- Program: `C:\path\to\python.exe`
- Arguments: `manage.py ez360_prune_backups`
- Start in: `C:\path\to\your\project`

---

## Record a restore test (evidence)

After you perform a restore to a staging/throwaway DB, record the result:

```
python manage.py ez360_record_restore_test --outcome pass --notes "Restored 2026-02-13 backup into staging; login + invoice list OK." --backup-file "ez360pm_db_20260213_021500.sql.gz"
```

If you record `--outcome fail`, EZ360PM creates an **Ops Alert** so it’s visible in Ops → Alerts.

---

## Restore drill command (operator checklist)

Print a step-by-step checklist (references the latest successful BackupRun):

```
python manage.py ez360_restore_drill
```

Optionally record outcome after you complete the drill:

```
python manage.py ez360_restore_drill --record-outcome pass --notes "Restored into staging; login + reports OK." --tested-by-email you@company.com
```
