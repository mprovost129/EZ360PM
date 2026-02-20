# EZ360PM Testing Guide

This guide is the **source of truth** for running tests locally (Windows) and in CI/production-style environments.

## 1) Quick Start

### Run the full test suite
```bash
python manage.py test
```

### Run a single app
```bash
python manage.py test documents
python manage.py test invoices
python manage.py test helpcenter
```

### Run a single test class or method
```bash
python manage.py test documents.tests.DocumentIsolationTests
python manage.py test documents.tests.DocumentIsolationTests.test_cross_company_edit_returns_404
```

### Stop on first failure + keep DB (faster iteration)
```bash
python manage.py test --failfast --keepdb
```

## 2) Recommended Testing Workflow (Phase 9)

### A. Every change pack (local)
1. **Unit/Smoke:**
   ```bash
   python manage.py test --failfast
   ```
2. **Migrations sanity:**
   ```bash
   python manage.py makemigrations --check --dry-run
   python manage.py migrate
   ```
3. **Static templates sanity (manual spot check):**
   - Footer legal pages: Terms / Privacy / Cookies / Security
   - Document composer: create/edit invoice, estimate, proposal
   - Banking review queue: create expense, link duplicate

### B. Before pushing / deploying
1. Run:
   ```bash
   python manage.py test
   ```
2. Run the **Launch Checks** (if present in your project):
   ```bash
   python manage.py check --deploy
   ```
3. Smoke the critical flows:
   - Client → Project → Time → Invoice → Payment → Reports
   - Trial/plan gating
   - Company isolation (cross-company UUIDs return 404)

## 3) What We Test (Current Coverage Targets)

### Must-pass (launch blockers)
- **Company isolation** (no cross-tenant access)
- **Legal/help pages** render (no TemplateDoesNotExist)
- **Document totals** are correct server-side (tax, deposits, balance)
- **Banking duplicate prevention** (link vs create)
- **Stripe webhook idempotency** (no double-post)

### Nice-to-have
- Role-based access controls (staff vs manager vs admin vs owner)
- PDF/print rendering
- Email sending stubs (in dev) + production settings checks

## 4) Common Failures & Fixes

### "TemplateDoesNotExist"
- Confirm the app is in `INSTALLED_APPS`.
- Confirm the template path uses the standard structure:
  `appname/templates/appname/template.html`

### "column ... does not exist"
- Migrations haven’t been applied:
  ```bash
  python manage.py migrate
  ```

### Storage errors (S3) during template rendering
- Never call `{{ field.url }}` directly unless you know the backend cannot throw.
- Use the project’s safe media URL helper/filter if available.

## 5) Optional: Test Settings Notes

- Use the project’s `dev` settings module locally.
- Ensure you have a test database available (SQLite is fine for most unit tests; Postgres recommended for integration tests).

