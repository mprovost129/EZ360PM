## 2026-02-18 — Phase 9 (P9-DASH-FOCUS-LISTS) — Dashboard Focus Lists + KPI Period Filter (DONE)

## 2026-02-21 — Admin experience overhaul (IN PROGRESS)

Goal: Replace reliance on raw Django Admin with an **EZ360PM-branded control panel** that cleanly separates:
- **Platform / Ops / Site config** (EZ360PM Settings)
- **Tenant-scoped customer data** with a **Company selector** (EZ360PM Customers)

Planned rollout:
1) Stand up two AdminSite portals + branding + sectioned index (DONE)
2) Add Company switcher + queryset scoping for company-owned models (DONE baseline)
3) Tighten registrations: only platform models in Ops admin; only tenant-scoped models in Customers admin (NEXT)
4) Add per-company “jump navigation” (quick links) and stronger guardrails (permissions + FK limiting edge cases) (NEXT)
5) Remove legacy `/admin/` once parity is reached (LATER)

## 2026-02-21 — Ops Center (Executive SaaS Ops) — Packs 1–5 (DONE FOUNDATION)

Goal: Build a **professional, executive-grade SaaS operations center** under `/ops/` for platform control.

Done (foundation):
- Pack 1: Light executive shell + KPI overview layout.
- Pack 2: Companies directory + Company 360 panel + support mode entry/exit.
- Pack 3: Suspension controls + force logout + ops action audit trail.
- Pack 4: Stripe action queue (approve/run/cancel) + Support Mode reason guardrails.
- Pack 5: Global Support Mode banner across app pages + support cap alignment.

Done (hardening + polish):
- Pack 6: Typed confirmations for high-impact ops actions + enhanced global Support Mode banner.
- Pack 7: Ops Companies segments + CSV export + critical bugfix.

Next (candidate Pack 8):
- Operational reports: churn, trial conversion, payment failures, webhook error rate.
- Saved filter presets stored per-operator (wire `OpsCompanyViewPreset` into UI).

## 2026-02-19 — DONE: UI Layer Consistency (CSS)

Applied an app-wide CSS layer consistency pass (navbar/sidebar/cards/inputs) without altering the active sidebar menu item color.
Acceptance: dashboard + key CRUD pages show clear hierarchy; forms have white inputs on soft card surfaces; nav + sidebar visually separated.

## 2026-02-19 — DONE: Company settings edit permission wiring

## 2026-02-19 — DONE: Dashboard quick actions dropdown

- Collapsed the “Quick actions” panel into a single **+ New** dropdown (Track time + manager actions).
- Keeps the right rail clean and reduces button clutter while preserving all shortcuts.
- Sidebar company dropdown: removed duplicate “Active company” label under the dropdown and added a **Switch company** item inside the dropdown.
- Dashboard right rail: ordered **Quick notes** above **Getting started** and removed legacy right-rail widgets (Outstanding invoices / Active company / Your role / Subscription) even if older saved layouts include them.

- Fixed `companies:settings` so owners/admins can edit.
- Added `CompanySettingsForm` and updated the view to pass `form` + `can_edit` (template required these).
- Read-only users now see disabled fields with a clear warning.


Goal: Make the dashboard read like a **financial + operations cockpit**: KPIs first, then the three lists that should be monitored daily.

What's included
- Added a **Period** filter (This month / Last 30 / Last 90 / YTD) that drives Revenue + Expenses KPIs.
- KPI cards now clearly display their **time basis** (Revenue/Expenses = selected period; A/R + Unbilled = "as of" today).
- Replaced the dashboard list panels with three high-signal sections:
  - **Outstanding invoices** (ordered by due date, earliest first; limited list)
  - **Recent open projects** (active only; completed excluded)
  - **Recent expenses** (latest spend activity)
- Updated dashboard widget registry defaults to match the new reading order.

Acceptance checks
- Dashboard loads with no errors; changing Period updates Revenue/Expenses card labels + totals.
- Outstanding invoices list orders correctly by due date.
- Open projects excludes inactive projects.
- Dashboard no longer shows the time-tracking panel.

---

## 2026-02-18 — Phase 9 (P9-DASH-RIGHT-ACTIONS) — Dashboard Right-Rail Quick Actions (DONE)

Goal: Move “Quick actions” into the right rail so the dashboard reads as a report on the left with actions always available.

Done:
- Updated dashboard widget registry: `quick_actions` now defaults to the **right** column with higher priority ordering.
- Updated dashboard layout resolver so “required” widgets are inserted into their widget-defined default column (prevents forced-left placement).

Acceptance checks:
- Dashboard renders with KPIs on the left and Quick actions in the right rail by default (new layouts).
- Existing custom layouts remain unchanged.

---

## 2026-02-18 — Phase 9 (P9-DOC-TAX-SERVER) — Server-side Tax Recalc for Composer (DONE)

Goal: Ensure document tax totals are correct even if JS is disabled and remain consistent when tax percent changes.

Done:
- Updated `documents.services.recalc_document_totals()` to recompute per-line tax and line totals using `Document.sales_tax_percent` for taxable lines (when > 0).
- Added a regression test covering server-side tax recomputation from `sales_tax_percent`.

Acceptance checks:
- Creating/saving a document with `sales_tax_percent > 0` recomputes taxable line `tax_cents` and `line_total_cents`.
- `python manage.py test documents` passes.

## 2026-02-18 — Phase 9 (P9-NAV-SMOKE) — Navigation + Legal Page Smoke Tests (DONE)

Goal: Prevent launch-blocking regressions (dead nav/footer links, missing templates, missing installed apps) by adding high-level smoke tests that load core public + authenticated entry points.

Done:
- Added `core/tests/test_nav_smoke.py`:
  - Public landing renders (including footer legal links).
  - Public legal pages return 200: Terms / Privacy / Cookies / Security.
  - Authenticated entry points load (or redirect when gating applies): dashboard, clients, projects, invoices, expenses, help center.

Acceptance checks:
- `python manage.py test core helpcenter` passes.
- Public footer links no longer regress silently (TemplateDoesNotExist / NoReverseMatch caught by tests).

## 2026-02-18 — Phase 9 (P9-BANK-DUPE-LINK) — Bank Review Duplicate-Link Action (DONE)

Goal: Prevent duplicate expenses during bank-feed review by making the “suggested existing expense” linkable in one click.

Done:
- Added a POST action to link a bank transaction to its suggested existing Expense (`/integrations/banking/tx/<id>/link-existing/`).
- Exposed a “Link suggested” button in the Bank Review Queue when a duplicate suggestion exists.
- Hardened single-transaction “Create expense” to refuse creation when there’s a strong duplicate suggestion (>=90 score) and direct users to link instead.

Acceptance checks:
- Review Queue shows “Link suggested” when a duplicate is detected.
- Linking marks the transaction as processed and redirects to the linked Expense.
- Creating an expense is blocked when a strong duplicate suggestion exists.

## 2026-02-16 — Phase 8C (DONE)
Table modernization pass:
- Standardized list tables to `table-hover` + `align-middle` + `ez-table`.
- Standardized row action columns to **icon buttons + dropdown** (less noise, consistent placement).
- Standardized document status badge styling via a shared template filter.

## 2026-02-17 — Phase 9 (P9-UI2) — UI Consistency Sweep + Timer Bug Fix (DONE)

- UI consistency:
  - Standardized remaining list/detail pages to use `card shadow-sm` so the Phase 8 card system applies everywhere.
  - Removed stray `bg-white` card headers where they override the standardized card header styling.
- Bug fix (Timer):
  - Fixed invalid nested `<form>` markup on the Timer page (prevents broken submits in some browsers).

## 2026-02-19 — Phase 9 (P9-DASHBOARD-PREMIUM) — Premium Dashboard Charts + Layout Defaults (DONE)

What we did:
- Added two new dashboard widgets:
  - `revenue_trend`: last 6 months cash-in (payments received)
  - `ar_aging`: A/R aging buckets for open invoices
- Added JSON endpoints:
  - `GET /app/dashboard/api/revenue-trend/`
  - `GET /app/dashboard/api/ar-aging/`
- Updated dashboard widget registry + defaults to match the "premium" layout:
  - `kpis` → `recent_invoices` → `recent_open_projects` → `revenue_trend` → `ar_aging` → `recent_expenses`
  - Kept `outstanding_invoices` available (moved to right rail by default).

Acceptance checks:
- Dashboard renders with no JS errors; charts fail gracefully if endpoints are unavailable.
- Revenue trend shows 6 months with USD tooltips.
- A/R aging buckets reflect open invoice balances.
- Premium users can still customize dashboard layout; non-premium users get sane defaults.

## 2026-02-18 — Phase 9 (P9-DOC-COMPOSER) — "Paper" Document Composer (DONE)

Goal: Make Invoice / Estimate / Proposal creation and editing look and feel like an **editable version of the final document** (a clean paper surface), while keeping fields wired to real data (client/project/catalog).

Done:
- Restored/added the missing `documents/document_edit.html` template and replaced the editor with a centered **paper-style** composer.
- Added a dedicated composer CSS + JS bundle:
  - Live subtotal/tax/total and per-line totals.
  - Optional invoice deposit guidance (percent or fixed) with live “balance after deposit”.
  - Add-line button that correctly increments Django formset `TOTAL_FORMS`.
- Kept dropdowns wired to real lists:
  - Client dropdown → CRM clients
  - Project dropdown → Projects
  - Service dropdown → Catalog items (auto-fill via `catalog:item_json`)
- Added base template extension points (`extra_css` / `extra_js`) so feature pages can include page-specific assets cleanly.

Acceptance checks:
- Create/Edit Invoice/Estimate/Proposal loads without TemplateDoesNotExist.
- Catalog selection auto-fills name/description/rate/taxable and updates live totals.
- Add line → save → line persists and totals recalc server-side.
- Deposit type/value persists on invoice and live values update while editing.

Next:
- Align PDF templates (`*_pdf.html`) to match the composer layout more closely.
- Optional: allow Terms block for proposals/estimates via per-doc-type setting.

## 2026-02-18 — Phase 9 (P9-DOC-PDF) — Customer-facing Print/PDF Export (DONE)

Goal: Make the customer-facing output match the paper-style composer and support **Print (HTML)** + **PDF download**.

Done:
- Added customer-facing template: `templates/documents/document_pdf.html` (Invoice / Estimate / Proposal).
- Added print/PDF endpoints:
  - `/documents/invoices/<id>/print/` + `/pdf/`
  - `/documents/estimates/<id>/print/` + `/pdf/`
  - `/documents/proposals/<id>/print/` + `/pdf/`
- PDF generation is **best-effort** via optional WeasyPrint; when missing, the PDF route falls back to Print view with a friendly message.
- Added document PDF styling: `static/css/document_pdf.css` (Letter page sizing + clean print rules).
- Added **Print** + **PDF** buttons to the composer toolbar.

Acceptance checks:
- Print view renders cleanly and prints on Letter with correct margins.
- PDF download works when WeasyPrint is installed; otherwise routes to Print view and shows a clear message.
- Output shows company header, client block, document meta, line items, totals, notes, and invoice terms.

## 2026-02-18 — Phase 9 (P9-DOC-PDF-PARITY) — Print/PDF Output Polish (DONE)

Goal: Keep the customer-facing Print/PDF output resilient and visually aligned with the composer.

Done:
- Added a real **Print** button on the HTML preview toolbar.
- Hardened branding logo rendering:
  - Uses `|safe_media_url`.
  - Falls back to the static EZ360PM logo when the media backend is misconfigured.

Acceptance checks:
- Print preview toolbar shows a working Print action.
- Print/PDF never 500s due to media storage endpoint misconfiguration.

## 2026-02-18 — Phase 9 (P9-DOC-TEMPLATE-BLOCKS) — Template Header/Footer Blocks (DONE)

Goal: Support template-driven **header/footer text blocks** that render in customer-facing output and are editable in the composer.

Done:
- Added `Document.header_text` and `Document.footer_text` fields (TextField).
- Wizard: when creating from a `DocumentTemplate`, copies `header_text` and `footer_text` into the new document.
- Composer: added editable "Header text" and "Footer text" blocks on the paper editor.
- Print/PDF output: renders the header block near the top and footer block near the bottom.

Acceptance checks:
- Create a document from a template and confirm header/footer populate.
- Editing header/footer in the composer persists after Save.
- Print/PDF shows header/footer blocks without layout breakage.

## 2026-02-18 — Phase 9 (P9-QA0-ISOLATION-TESTS) — Company Isolation Regression Tests (DONE)

Goal: Lock in the **company isolation** invariant with automated tests so Phase 9 QA regressions are caught early.

Done:
- Added regression tests ensuring a valid company is auto-selected when missing from session on a company-scoped page.
- Added cross-company access tests for Documents: attempting to edit/print another company's document returns **404**.

Acceptance checks:
- `python manage.py test companies documents` passes.
- Attempting to access a document UUID from another company returns 404 (no data leakage).

## 2026-02-18 — Phase 9 (P9-LEGAL-SMOKE) — Legal Pages Smoke Tests (DONE)

Goal: Prevent regressions where `/legal/*` pages 500 in production (e.g., missing templates).

Done:
- Added `helpcenter/tests.py` smoke tests asserting all public legal pages return HTTP 200.

Acceptance checks:
- `python manage.py test helpcenter` passes.
- `/legal/terms/` renders in production.

## 2026-02-16 — Phase 8D (DONE)
Forms UX upgrade:
- Implemented sticky form footer pattern (Cancel + Save) via `templates/partials/form_footer.html`.
- Added `.ez-form`/`.ez-form-footer` styling to keep primary actions visible.
- Updated key forms (Client, Project, Catalog item, Document edit) to use consistent sectioning and actions.

## 2026-02-16 — Phase 8E (DONE)
Empty states + first-run guidance:
- Replaced plain “No results” table rows with intentional empty states (icon + title + CTA) on:
  - Expenses
  - Payables (Vendors, Bills)
  - Expenses → Merchants
  - Payables → Recurring bill plans
- Improved Dashboard empty panels with clear CTAs (Create invoice, Start timer/Add time).
- Enhanced `includes/empty_state.html` to support custom icons.

## 2026-02-16 — Phase 8F (DONE)
Micro-interactions polish:
- Auto-dismiss non-critical flash alerts after a short delay (success/info).
- Added a global submit-guard: disables submit buttons on POST to prevent double-submits and shows an inline spinner.
- Added a lightweight confirm helper via `data-ez-confirm` for destructive actions (opt-in per link/form).

## 2026-02-16 — Phase 8G (DONE)
Help Center UX + discoverability:
- Added Help dropdown in the top-right app navbar (quick links to Help/Getting Started/FAQ/Terms/Privacy).
- Updated the public navbar Help link to route to the in-app Help Center.
- Added in-page Help sidebar search (client-side filter) to quickly find guides and legal pages.

### Next (Phase 8H)
Completed in Phase 8H.

### Next (Phase 8I)
- Mobile polish: long table overflow + action dropdown spacing.
- Final UI consistency pass on high-traffic pages (Invoices, Payments, Time) once mobile fixes land.

## 2026-02-17 — Phase 8H (DONE)
## 2026-02-17 — Phase 8I (DONE)
Mobile polish:
- Made topbar actions popover fit small screens (no off-screen overflow).
- Made Timer dropdown menu responsive on phones (full-width within viewport).
- Ensured tables remain readable on mobile by enforcing a minimum scroll width within `.table-responsive`.
- Improved sticky form footer behavior on iOS via safe-area padding.

Brand pass (Bootstrap-aligned):
- Introduced Bootstrap CSS variable overrides to align primary/success/link/border/body tokens with EZ360PM brand.
- Added brand-aligned primary/outline button styling (subtle gradient) while remaining Bootstrap-compatible.
- Standardized form control radius + focus ring for a “financial-grade” feel (light and dark themes).
- Normalized card footer styling to match the new card system.

## 2026-02-17 — Phase 8J (DONE)
Launch Gate seeding + UX:
- Added a default Launch Gate checklist seed list (`ops/launch_gate_defaults.py`).
- Added a staff action to seed items from the Launch Gate page (safe/no-overwrite).
- Added management command `python manage.py ez360_seed_launch_gate` for environments where staff UI isn’t ideal.

## 2026-02-16 — Phase 7H46 (DONE)
- Help Center: added an admin-facing checklist page for required screenshot keys at:
  - `/admin/helpcenter/helpcenterscreenshot/required-keys/`
  - Keys are tracked in `helpcenter/required_screenshots.py`.
- Ops: dashboards now show snooze “until” timestamps inline and provide a one-click **Clear** action.
- Statements: added per-client **Collections notes** (with optional follow-up date) on the Client Statement page.

## 2026-02-16 — Phase 7H47 (DONE)
- Statements: added company-wide **Collections Follow-ups Due** queue (open notes where `follow_up_on <= today`) with search + “Mark done” flow.
- Ops: added **Alert Snoozes** list/detail for audit visibility, plus delete/clear actions.
- Ops: added expired snooze cleanup via `ez360_prune_ops_snoozes` and SiteConfig retention `ops_snooze_prune_after_days`.

## 2026-02-16 — Phase 7H48 (DONE)
- Ops: fixed missing `staff_only` decorator in `ops/views.py` (prevents import-time crash on alert views).
- UX: added navigation links to Collections follow-ups and Snoozes from relevant pages.

## Phase 8 — Launch Prep & UI Modernization

## 2026-02-16 — Phase 8A (DONE)
UI foundation hardening (launch prep):
- Global card standardization: all `card shadow-sm` now render as borderless, rounded cards.
- Sidebar polish: active nav highlighting is automatic (JS marks active link) with a subtle left indicator bar.
- Page header typography helpers (`.ez-page-title`, `.ez-page-subtitle`) applied to key pages.
- Table polish: key list pages use a consistent table style (`table-hover` + `align-middle`).

## 2026-02-16 — Phase 8B (DONE)
Dashboard redesign pass:
- Added a KPI row (Revenue, Expenses, A/R, Unbilled hours) with current month label.
- Added Recent Invoices + Recent Time panels.
- Added Due-soon Projects panel.
- Wired dashboard view metrics so the dashboard is context-complete (no missing variables).

## 2026-02-16 — Phase 8C (DONE)
Table modernization pass:
- Standardized list tables to `table-hover` + `align-middle` + `ez-table`.
- Standardized row action columns to **icon buttons + dropdown** (less noise, consistent placement).
- Standardized document status badge styling via a shared template filter.



## 2026-02-16 — Phase 7H29 (DONE)
- Daily ops checks now create Ops Alerts + optional admin emails on failures.
- Added Help Center content for Profit & Loss, Balance Sheet, Trial Balance + contextual report Help buttons.

## 2026-02-16 — Phase 7H30 (DONE)

- Added Client Statements (open invoices) with CSV export and optional PDF export (WeasyPrint if installed).
- Added statement email send (templated) from Statement page.
- Help Center: role-based workflow guidance + screenshot placeholders for Time/Invoices/Accounting/Statements.
- Ops: DB-backed alert routing (email/webhook) with staff UI + Ops Dashboard recent alerts list.


## Phase 7H31 — Statements polish + Ops deep links + Template sweep (DONE)

- Template sweep: fixed remaining `{% url %}` un-namespaced usage (404/500) and removed invalid parentheses in `{% if %}` blocks.
- Statements polish:
  - Added optional date-range filter (issue date; falls back to created date when issue date missing).
  - CSV/PDF exports honor the same date range.
  - Statement email now includes an optional “View statement” link back into the app (requires `SITE_BASE_URL`).
  - PDF includes optional period + “View online” link (requires `SITE_BASE_URL`).
- Ops:
  - Added per-alert detail page and deep links from Ops Dashboard recent alerts list.
  - Added “Send test alert” panel on Ops Dashboard to exercise routing.
  - Added new alert source `ops_dashboard`.
- Help Center:
  - Replaced screenshot placeholder text with actual placeholder images under `static/images/helpcenter/` (ready to swap with real screenshots).

## Phase 7H32 — Statement PDF/email hardening + readiness + Ops copy JSON (DONE)

- Statements:
  - Added optional “Attach PDF” checkbox for statement emails (WeasyPrint-only).
  - Improved statement PDF styling for print (Letter sizing, margins, page numbers, cleaner header/table layout).
  - Fixed statement PDF/email redirect flows and querystring handling.
- Readiness:
  - Added `SITE_BASE_URL` check (warns when blank with DEBUG=False) so email deep links are reliable.
- Ops:
  - Added alert detail links in the Ops Alerts list table.
  - Added “Copy JSON” button on alert detail page.
- Help Center:
  - Screenshot placeholders remain in place; next phase will swap in real screenshots.

## Phase 7H33 — Statement email preview + PDF error hints + Ops JSON download + Help screenshots (DONE)

- Statements:
  - Added **Email preview** modal on Client Statement page (renders HTML + text preview via JSON endpoint; no email is sent).
  - Improved PDF failure messages to differentiate **WeasyPrint missing** vs **render/deps failure** (Cairo/Pango hints).
- Ops:
  - Added **Details JSON download** endpoint (`details.json`) from Alert Detail.
  - Added **Request ID correlation** display when present in alert details with one-click copy.
- Help Center:
  - Began swapping screenshot placeholders for richer placeholder images for **Time Tracking**, **Invoices/Payments**, and **Statements**.

## Phase 7H34 — Help Center Accounting screenshots + Statement inline warnings + Ops alert filter affordances (DONE)

- Help Center: replaced remaining Accounting screenshot text with placeholder screenshot cards (Chart of Accounts, Journal Entries, Reports, General Ledger) and removed all "[Screenshot: ...]" text blocks.
- Statements: added inline warning banner on the Statement page when `SITE_BASE_URL` is missing and/or WeasyPrint is not installed.
- Ops: made alert KPI cards clickable quick-filters (open + source) while preserving querystring-based filters.

## Phase 7H35 — Ops alert pagination + bulk resolve + statement recipient defaults + finance help permissions (DONE)

- Ops Alerts:
  - Added server-side pagination (50/page).
  - Added bulk resolve (selected IDs or filtered up to 500).
- Statements:
  - Added “Send test to myself” action.
  - Persisted last-used statement recipient per client (per company) and prefill it next time.
- Help Center:
  - Added permissions table to core finance/reporting pages.

## Phase 7H36 — Statement reminders + Ops noise filters + alert pruning (DONE)

- Statements/Collections: added **StatementReminder** scheduling hook (schedule/cancel per-client reminders) + management command `ez360_send_statement_reminders`.
- Ops: added **noise filters** (ignore path prefixes / user-agent tokens) and wired them into alert creation (best-effort).
- Ops: added **alert pruning** management command `ez360_prune_ops_alerts` for resolved alerts older than N days (default from Ops SiteConfig).


## Phase 7H37 — Scheduling guidance + Statement reminder presets (DONE)

- Help Center: expanded Production runbook scheduling section with Render cron recommendations for:
  - `ez360_run_ops_checks_daily`
  - `ez360_send_statement_reminders`
  - `ez360_prune_ops_check_runs`
  - `ez360_prune_ops_alerts`
- Statements: added reminder tone presets (Friendly nudge vs Past due) and corresponding email templates.

## Phase 7H38 — Ops cron guidance + Statement cadence helper (DONE)

- Ops: added copy/paste **Render cron job** guidance + link on Ops Checks page.
- Statements: added reminder **cadence helper** (quick-pick dates) and displayed **last sent reminders** on the Statement page.
- Help Center: placeholder screenshots remain until post-launch (real screenshots task deferred).

## Next (Phase 7H39)

## Phase 7H39 — Reminder attempt visibility + failed reschedule + Ops scheduler sanity (DONE)

- Statements/Reminders:
  - Added `attempted_at` + `attempt_count` fields to `StatementReminder` so failures have clear “last attempt” metadata.
  - Reminder sender command now records an attempt timestamp/counter even on failures.
  - Statement page now shows a **Failed attempts** table (with last error) and a **one-click reschedule** action.
- Ops:
  - Ops Dashboard now includes copy/paste cron commands (same list as Ops Checks).
  - Added scheduler/env sanity warnings (SITE_BASE_URL + email backend/SMTP placeholder checks).
- Help Center:
  - No content changes in this phase (still pending real screenshots once UI is stable).

## Phase 7H40 — Statement retry UX + scheduler readiness expansion (DONE)

- Statements:
  - Failed reminders table now includes an optional **reschedule-to-date** input (defaults to +7d if blank).
  - Added **Retry now** (staff-only) action for a single failed reminder (synchronous send + attempt tracking).
- Ops:
  - Extended scheduler/env sanity warnings to include **Stripe**, **S3/storage**, **backup storage**, and **domain alignment** checks.
- Help Center:
  - Screenshot placeholders remain until post-launch; begin swapping once UI is stable.

## Phase 7H41 — Statement audit trail + copy email + Ops alert dedup/snooze (DONE)

- Statements:
  - Added per-reminder **audit trail** (Scheduled by / Updated by + timestamp) on the Statement page.
  - Added **“Email me a copy”** option for statement sends (best-effort copy to acting user).
- Ops:
  - Added **alert deduplication window** (SiteConfig `ops_alert_dedup_minutes`).
  - Added **snooze** for alerts (OpsAlertSnooze + UI action from alert detail).
- Help Center:
  - Screenshot replacement is still pending; will be done after UI stabilizes.

## Phase 7H42 — Statement tone preview + Reminder bulk actions + Ops export/quick snooze (DONE)

- Statements:
  - Statement email send now supports selecting **Tone**: Standard / Friendly nudge / Past due.
  - Statement email preview modal now previews the selected **Tone** (HTML + text) before sending.
  - Reminder scheduler includes a **Preview reminder email** action (uses the selected tone + optional PDF attachment).
  - Added company-wide **Statement Reminders** queue with bulk actions:
    - Cancel selected
    - Reschedule selected
- Ops:
  - Alerts list now shows **dedup_count** ("Dup" column) when alerts were deduplicated.
  - Added **quick snooze** dropdown from the alerts list (30m / 2h / 1d).
  - Added **Export CSV** for unresolved alerts (respects filters; capped).
- Help Center:
  - Prepared wiring for swapping placeholder images; actual screenshots pending UI stabilization.

## Phase 7H43 — Reminder bulk send-now + delivery report + Ops grouping summary (DONE)

- Statements:
  - Added **bulk “Send now”** action for selected reminders (staff/admin-only).
  - Added **Reminder delivery report** (last 30 days: sent/failed by day) to the reminders queue.
- Ops:
  - Added **Open alerts summary** grouped by **source** and **source+company** for fast triage.
- Help Center:
  - Screenshot swapping remains pending until we capture real UI screenshots post-freeze.

## Phase 7H44 — Filtered send-now + client statement history + ops company filter (DONE)

- Statements:
  - Add “send now” for **filtered set** (not just selected) with safety cap + confirm checkbox.
  - Add per-client statement history (last sent / last viewed) on client detail.
- Ops:
  - Add company filter to Ops Alerts list (company_id) and preserve it in links.
  - Add source/company snooze from the grouping summary.
- Help Center:
  - Replace placeholder images with real screenshots for the top workflows (Invoices, Time, Projects).

## Phase 7H20 — Template/Static sanity + Readiness staticfiles (DONE)

- Template sanity command fixed and expanded (money/static tag load checks, invalid-if parentheses warning).
- Readiness check expanded to validate `STATIC_ROOT` existence and writability (prod gate).

## Phase 7H21 — URL sanity check + Ops wiring (DONE)

- Added management command `ez360_url_sanity_check` to validate `{% url %}` names referenced in templates (best-effort).
- Added Ops → Checks checkbox to run URL sanity and store evidence.
- Fixed Ops forms indentation regression and migrated drift forms to UUID company IDs.

## Phase 7H23 — Help Center fill + Template sanity expansion + Ops evidence export (DONE)

- Template sanity scan expanded:
  - Warn on POST forms missing `{% csrf_token %}`.
  - Warn on `{% url %}` tags using un-namespaced view names (heuristic).
- Help Center pages added:
  - Recurring Bills
  - Refunds
  - Ops Console
- Ops Checks: added “Export recent runs” ZIP bundle (includes runs.csv + per-run output files).

## Phase 7H24 — URL arg-count heuristics + Contextual Help deep links + Ops daily scheduler + retention (DONE)

- Expanded `ez360_url_sanity_check` to (best-effort) validate positional argument counts for the top 20 most-used `{% url %}` tags and warn on obvious mismatches.
- Added contextual Help deep links:
  - Payables → Recurring bills now links to Help Center → Recurring Bills.
  - Payments → Payment/Refund screen links to Help Center → Refunds.
  - Payables → Bill detail includes Help Center → Accounting link.
- Added scheduler/retention commands:
  - `python manage.py ez360_run_ops_checks_daily` (persist OpsCheckRun evidence; intended for daily cron/scheduler)
  - `python manage.py ez360_prune_ops_check_runs --days 30` (Ops evidence retention)
- Help Center → Ops Console updated with automated daily checks guidance.

## Phase 7H25 — Ops actions + URL sanity kwargs + Help Center A/P (DONE)

- Ops → Checks: added buttons for "Run daily checks now" and "Prune ops runs" (staff-only).
- URL sanity: added best-effort kwarg validation and namespaced-variant warnings for un-namespaced url names.
- Help Center: added Bills (A/P), Vendor Credits, and A/P Reconciliation pages and linked them from Help Home.


## Phase 7H26 — Help Center A/R + contextual help (DONE)

- Help Center: added Accounts Receivable, Client Credits, and A/R Aging pages and wired them into Help Home and Help sidebar navigation.
- Reports: Accounts Aging report now includes a contextual Help button (Help Center → A/R Aging).

## Phase 7H27 — Help Center A/R workflows + A/P Aging help + Production runbook (DONE)

- Help Center: added Collections, Statements, and Report interpretation pages for A/R workflows.
- Help Center: added A/P Aging page; A/P Aging report now has a contextual Help button.
- Help Center: added Production runbook (deploy + daily ops + scheduling notes).

### Next (Phase 7H28)
- Expand “Statements” into an exportable PDF/email workflow (optional) and add a lightweight client statement view.
- Add Help Center content for P&L / Balance Sheet / Trial Balance pages with screenshots/definitions.
- Add optional Ops alert routing (email + webhook) for failing daily checks.


## 2026-02-16 — Phase 7H15 (DONE)
- Ops Console: fix seat limit display by computing seats limit via `seats_limit_for()`.

**Next:**
- Continue launch hardening: fill Help Center content, finalize email templates/subjects, expand invariants & readiness evidence, and run end-to-end ops checks on staging/prod.

## 2026-02-16 — Phase 7H7 (DONE)
- Payment refund posting hardening: missing `Sum` import fixed.
- Refund proration math moved to integer-safe allocation (no float drift).

## 2026-02-16 — Phase 7H8 (DONE)
- Timer persistence expanded: last timer selections now persist in `TimeTrackingSettings` and rehydrate if `TimerState` is recreated.
- Added staff-only Ops Checks UI (/ops/checks/) to run: smoke test, invariants, idempotency scan.
- Added `ez360_idempotency_scan` management command to detect missing/duplicate journal provenance (NULL-safe).

## 2026-02-16 — Phase 7H9 (NEXT)
- Posting provenance audit: ensure every auto-posting source sets `JournalEntry.source_type/source_id` consistently.
- Extend Ops Checks page with “Company picker” + recent run history.
- Add CI-friendly flags to ops checks (quiet/fail-fast) and wire to launch evidence.

## 2026-02-16 — 2026-02-16 — Phase 7H4 (Ops-grade invariants + admin polish)
**Done:**
- Admin money formatting completed for: CRM Clients, Payables (Bills/Line Items/Payments/Recurring Plans), Payments (credits, applications, refunds), Accounting journal line inlines.
- Invariants expanded:
  - Payments/refunds sanity
  - JournalEntry provenance sanity (source_type requires source_id)
- Timer UI: added “Manage catalog services” link (Manager+).

**Next (Phase 7H5):**
- Expand invariants further:
  - invoice net paid vs refunds
  - credit ledger vs applications vs effective balance
  - posting idempotency cross-checks (document/payment/expense unique source entries)
- Finish remaining admin polish:
  - Expenses admin money columns
  - Credit ledger and refund filters/search improvements
- Timer UX: persist last selections across stop/start (confirm TimerState fields are kept) and add “Open project” shortcut.

## 2026-02-16 — Phase 7G5 (Money UX normalization for Projects & Documents)
**Done:**
- Projects + Documents money fields migrated to `MoneyCentsField` (dollars UI, cents storage).
- Fixed `|money` template filter alias so dashboards and lists render correctly.

**Next (Phase 7H):**
- Expand money UX standard across remaining modules (invoices summary, reports, payables edge cases).
- Strengthen invariants + smoke tests:
  - document totals match line items (subtotal/tax/total)
  - project billing rates correct across create/edit
- Time tracking UX hardening:
  - navbar timer: add “service on the fly” (creates CatalogItem) and persist last selections.
- Ops:
  - add a `manage.py readiness_check` command for env + migrations + storage + email sanity.

## 2026-02-15 — Phase 7G complete
**Done:**
- Unified private download/open link behavior across receipts, project files, and bill attachments via shared helper (`core/services/private_media.py`).
- Added optional inline preview for PDFs/images using presigned S3 URLs (`?preview=1`), plus UI Preview buttons where applicable.

**Next:**
- Phase 7H: A/P payments workflow expansion (checks / vendor credits) if matching QuickBooks parity.
- Phase 7I: tighten financial audit trails around payables (payment posting, void/reversal workflows) and reporting parity.



# EZ360PM Roadmap (Locked After Phase 3A Layer 2)


## Current Hardening Track (Phase 3F → Launch)

### Completed
- **3F** Financial integrity + credit notes + reconciliation (baseline)
- **3G** Backup & Recovery (DB dump + optional media + retention + soft-delete guardrails)
- **3H** Monitoring & Observability (healthz, request-id, slow request logging, optional Sentry)
- **3I** UX polish (onboarding checklist, dismissible alerts, cleanup)
- **3J** Client Credit Ledger + Auto-Apply Credit
- **3K** Ops Console + Support Mode (staff-only)
- **3L** Ops Timeline + Stripe Subscription Diagnostics (staff-only)
- **3M** Refund Linkage (refunds tied to payments/invoices; balance + journal recalcs)
- **3N** Accounting Period Locks (Professional+; admin+; enforcement)
- **3O** Advanced Reporting Enhancements
- **3P** Launch Readiness Checks (staff-only UI + ez360_check command)
- **3Q** Ops Retention & Pruning (staff-only UI + ez360_prune command)
- **3R** Security Defaults (production-on email verification gate, secure cookies/HSTS/SSL defaults, default company 2FA policy)
- **3S** Financial Integrity + Invoice Reconciliation (manager+)
- **3T** Ops Alerts + Session Hardening (admin alerts on webhook/email failure; session key rotation on login)
- **3U** UX Perf Polish: pagination across major lists + CSP rollout fix (report-only toggle + jsDelivr allowlist)
- **3V** Performance indexing (Payments + client credit tables)
- **3W** Lightweight perf checks + Docs/TimeEntry indexes
- **3X** Settings profiles fix (dev/prod separation restored)
- **3Y** Dev HTTP/HTTPS usability fix
- **4A** Observability (healthz + Sentry init + env docs)
- **4B** Ops alerts expansion + perf sampling to DB
- **5A** UX premium: Getting started page + nav progress
- **6D** S3 direct uploads + project file workflow (presigned POST to private bucket)
- **6E** UI polish (state dropdown styling, project label display), currency input UX for Project rates, and timer dropdown in navbar
- **6G** Ops SLO dashboard (active users via presence pings) + optional external ops alert webhook notifications
- **6G1** Render migration hotfix (billing index rename idempotent + create-if-missing)
- **6H** Ops: PII export (company CSV ZIP) + SLO webhook freshness metrics
- **6I** Security: enforce 2FA for Admin/Owner roles (step-up confirmation on company-scoped pages + login flow supports 2FA)
- **6J** Production staticfiles hardening (WhiteNoise + hashed/compressed static; fixes Render admin/app CSS)
- **6K1** Mobile topbar fix + Sentry init (responsive logo sizing, safe-area insets; Sentry init enabled when DSN set)
- **6O2** Clients pagination hotfix (guarded previous/next page evaluation)
- **6P** Monitoring gate: Ops Probes (Sentry test error + test alert) + launch check evidence
- **6R1** UI/Perf hardening: invoice reconciliation CTA + staff clients subquery optimization
- **6S** 2FA policy optional (admin-configurable only) + Projects performance indexes (assignee/client/updated)
- **7A** Accounts Payable foundation (new payables app: Vendors, Bills, Bill Payments, auto-posting)
- **7B** Vendor unification + vendor ledger + dashboard payables widget
- **7C** A/P Aging report (UI+CSV) + Bill attachments (direct-to-S3 private keys)
- **7D** Secure bill attachment downloads (presigned GET) + UI download action

### Next (Planned)
- **Backup & Recovery Gate**: automated DB backups on Render, retention policy verified, and a documented restore test.
- **Monitoring Gate**: confirm Sentry capture in production + add an ops “test error” button for staff.
- Optional: move CSP from report-only to enforced after validating allowlist.

---

# COMPLETED

Phase 1 – Security Hardening
Phase 2 – Production Hardening
Phase 3A – Financial Integrity Layer 1 & 2

---

# NEXT PHASE (Planned)

Phase 3B – Credit Note System (Proper Integration)
- Model
- Migration
- Posting service
- UI endpoint
- Audit logging

Phase 3C – Reconciliation Dashboard
- Stripe vs Internal comparison
- Invoice balance diagnostics

---

# FUTURE PHASES

Phase 4 – Monitoring & Observability Expansion
Phase 5 – UX Premium Polish
Phase 6 – Client Portal Expansion
Phase 7 – Desktop Sync Reintegration

---

Current focus: Stabilize financial core before expansion.


## Phase 3D
- Credit Note UI (create + post)
- Invoice edit integration


## Phase 3E
- Credit note UI hardening + money formatting + numbering


## Phase 3F
- Credit note edit (draft-only)
- Dollar input UX
- Invoice activity timeline


## Phase 3G
- Backup & recovery pack: ez360_backup command + retention settings + restore runbook
- Soft-delete guardrails (SyncModel.delete defaults to tombstone)


### Phase 3H — Monitoring & Observability (DONE)
- Sentry optional integration
- /healthz DB health endpoint
- request ids + slow request logging
- webhook + email failure logging


### Phase 3I - UX & Premium Experience (DONE)
- Dashboard onboarding checklist with progress + next-step CTA.
- Dismissible alert messaging with safer tag mapping.


Next recommended hardening priorities:
- Customer credit auto-apply engine (rules + visibility) to reduce A/R friction.
- Accounting period locks to prevent back-dated changes.
- Advanced reporting enhancements (cashflow, utilization, job-costing).

### Phase 3J+ — Subscription Tiers & Feature Gating (DONE)
- Updated subscription model to Starter/Professional/Premium + Monthly/Annual.
- Added extra seat quantity support (included seats + add-on seats).
- Implemented `tier_required` decorator and centralized feature gating rules.
- Gated Accounting to Professional+ and Dropbox Integration to Premium (future feature).
- Updated Stripe checkout + webhook sync to use plan/interval + infer add-on seats.

## Phase 3K — Ops Console (DONE)
- Staff-only Ops Console (/ops/) with company search + quick Support Mode entry.
- Add follow-ups later: deeper subscription debugging (Stripe IDs), event/audit timeline, and “impersonate user” workflow with explicit banners + audit log.


## Completed – Phase 3M (Refund Linkage)
- Payment refunds: data model, UI entry point, balance recalculation, and accounting reversal entries.
- Next: accounting period locks + advanced reporting enhancements.


## Phase 3N — Accounting Period Locks (DONE)
- Added AccountingPeriod model and UI to create/close periods.
- Enforced closed-period rules across journals/invoices/payments/expenses.
- Professional+ tier; Admin+ role.


## Phase 3O — Advanced Reporting Enhancements (DONE)
- Added CSV export (?format=csv) for core accounting reports.
- Added Premium report: Project Profitability (journal-based, by project) with CSV export.

## Phase 3P — Launch Readiness Checks (DONE)
- Added staff-only Launch Checks page under Ops Console.
- Added `python manage.py ez360_check` management command for deploy validation (non-zero exit on errors).

## Phase 3Q — Ops Retention + Alerts (DONE)
- Added retention policy + pruning tooling (CLI + Ops UI).
- Added ops report runner for alert-style emails.

## Phase 3R — Security Defaults (DONE)
- Production-on defaults for email verification + secure cookies/SSL/HSTS (env overridable).
- Production default for 2FA requirement for admin/manager roles (env overridable).

## Phase 3S — Financial Integrity + Reconciliation (DONE)
- Added invoice reconciliation view and “recalculate” affordance.
- Hardened journal posting immutability and balance checks.

## Phase 3T — Ops Alerts + Session Hardening (DONE)
- Best-effort admin alerts for webhook/email failures (production-on defaults).
- Session key rotation on password login.

## Phase 3U — Pagination + CSP (DONE)
- Shared pagination helper + UI applied across major list pages.
- Fixed CSP settings typing and added env toggles; report-only defaults in production.

## Phase 3V — Performance Indexing (DONE)
- Added missing DB indexes for Payments + Client Credit ledger/application tables.
- Fixed `ClientCreditApplication` index declaration (was not in Meta; indexes were not being created).

## Phase 3W — Perf Sanity Checks + Documents/TimeEntry Indexes (DONE)
- Added dev-only per-request perf logging middleware (slow requests + slow ORM queries; env-driven thresholds).
- Added `python manage.py perf_check` management command for repeatable queryset benchmarks.
- Added Postgres partial indexes for Documents and TimeEntry list filters (ignoring soft-deleted rows).

## Phase 3X — Settings Profiles Fix (DONE)
- Restored clean settings layering (base/dev/prod) so local dev remains reliable.
- Removed base→dev import shim behavior and hard-coded hosts.
- Centralized DEBUG-derived defaults in `apply_runtime_defaults()` and re-run in dev/prod after setting DEBUG.

## Phase 3Y — Dev HTTP/HTTPS Access Fix (DONE)
- Dev no longer gets forced into HTTPS redirects due to production-style env values.
- `config/settings/dev.py` defaults to HTTP access and supports explicit local HTTPS testing via `DEV_SECURE_SSL_REDIRECT=1`.

## Next hardening items (after Phase 3S)

- [ ] Add links to Reconciliation from invoice detail screen (UI affordance).
- [ ] Add staff-only “Create correcting journal entry” tooling (optional v1, but useful).
- [ ] Expand data integrity: block edits to invoices/line-items after SENT, except controlled actions (void, credit note, refunds).
- [ ] Add lightweight performance checks (query counts on dashboard/report pages).

## Next hardening items (after Phase 3Y)

- [ ] Review Projects + Clients list filters and add indexes if needed (based on actual queryset usage).
- [ ] Add a small set of targeted prefetch/select_related improvements for any remaining N+1 hotspots found by perf logs.
- [ ] Consider Postgres trigram search (optional) if search boxes become a real perf hotspot.

- [x] Phase 4A — Monitoring & Observability
  - [x] Add `/healthz/` endpoint with DB + cache checks
  - [x] Add Sentry wiring (env-driven, safe import) for dev/staging/prod
  - [x] Complete `.env.example` with all required env vars

Next (Phase 4B):

- [x] Phase 4B — Ops Alerts + Perf Sampling (DB-backed)
  - [x] Staff-only Ops Alerts page (open/resolved, filters, search, resolve)
  - [x] DB alerts for Stripe webhook failures + email send failures
  - [x] Optional slow-request sampling stored to DB (env-driven)

Next (Phase 4C):
- [x] Add rate-limit and abuse dashboards (top throttles, 2FA/verify failures, repeated bad login) (staff-only).
- [x] Add “system status” widget on Ops Console (healthz last check, Sentry DSN presence, email backend mode).



- 5B Sensible defaults + empty states (DONE)

- [x] Phase 6A — Launch readiness gate UI + smoke test (DONE)


## Phase 6B — Completed (2026-02-13)

- Invoice lock enforcement (model + line items + view guard + UI banner)
- Ops reconciliation console (staff-only)
- Smoke test includes immutability verification
- Minor bug fixes (payments audit prev_balance; accounting ValidationError import)

### Next suggested: Phase 6C
- Refund/adjustment guardrails (partial refunds + journal postings) and Stripe idempotency checks
- Basic “unapplied payments” admin tooling (apply/void) to clear reconciliation drift

## Phase 7A — Release Discipline (DONE)

- [x] Add `/version/` endpoint for safe build metadata.
- [x] Add build metadata env vars (APP_ENVIRONMENT, BUILD_VERSION, BUILD_SHA, BUILD_DATE) and document them.
- [x] Launch checks warn in production if build metadata is missing.
- [x] Add `python manage.py ez360_preflight` for CI/staging/prod pre-deploy verification.


## Phase 7B — Release Notes + Preflight Migration Guard (DONE)
- Ops page for release notes + build metadata visibility.
- Preflight fails when pending migrations exist (default).


- [x] Phase 7C — Correlated logging + production security checks (launch checks)


### Phase 6D — Backup automation command (DONE)
- `ez360_backup_db` management command + env documentation.

## Hardening – Backup & Recovery
- [x] Wire backup/prune commands into host scheduler (cron/Render job) for daily backups + weekly prune.
- [x] Record a restore test (Ops → Backups or `ez360_record_restore_test`) after the first production backup is taken.
- [x] Optional: add S3 backup target (DONE 2026-02-15) if host snapshots are insufficient.


## 2026-02-13 — Completed: Phase 6C (Drift Toolkit + S3 Multi-Bucket)
- Ops Drift Toolkit + remediation actions (recalc, post-missing, link payment).
- S3 multi-bucket support (public/private).

## 2026-02-13 — Completed: Phase 6C.1 (Private downloads)
- Private bucket downloads now use presigned URLs (configurable expiry) and are routed through permission-gated app endpoints.
- Expenses now include a receipt “paperclip” action to open the attached receipt securely.

### Next: Phase 6E — Storage visibility + cleanup
- Ops → Storage page: show S3 config health, buckets, locations, and a "test upload"/"test download" check.
- Optional: lifecycle/retention policies for private bucket (host-level) + report guidance.
- Optional: direct-upload support for additional attachments (documents, proposals) if needed.

## 2026-02-14 — Completed: Phase 6F (Services catalog + timer pause/resume)
- Project Services now use CatalogItem(Service) dropdowns with optional custom names.
- Navbar timer displays project + live elapsed and supports pause/resume.

## 2026-02-15 — Completed: Phase 6K2 (Timer dropdown fix + locked invoice UX)
- Timer dropdown no longer relies on Bootstrap dropdown JS; uses deterministic local toggle logic.
- Locked invoices render read-only (disabled fields/line-items + no Save) to match financial invariants.

## 2026-02-14 — Completed: Phase 6F.2 (Error page resiliency)
- Added `templates/_public_shell.html` shim so 404/500 pages render in production.

### Next: Phase 6G — Service Catalog UI + timer-to-invoice workflow
- Add an in-app (non-admin) Service Catalog screen (CRUD, active toggle).
- Add “Allocate time by service” editor on time entry detail (splitting minutes across services).
- Add “Convert time to invoice line items” mapping service→rate + description.

## Done (2026-02-14)

- Render migration hotfix: billing 0003 index rename/create now idempotent.
- Error page stability: `_public_shell.html` shim + 404/500 link fixes (no `dashboard:` namespace dependency).
- Email verification resend: fixed URL ordering + login requirement + ops alert on failures.

## Next

- Phase 4 (Monitoring & Observability): verify Sentry wiring in production, validate Ops alerts for **email** + **webhooks**, and add a small “send test email” button in Ops to confirm provider config end-to-end.
- Phase 5 (UX polish): standardize remaining form select styling + money widgets across invoices/estimates/expenses.

## Next (immediate)
- **Phase 6E (Storage visibility):** Ops → Storage health page + “test presign/upload/download” button.
- **Phase 6M (Email diagnostics):** Ops “Send test email” button + Launch Check for SMTP/provider config + webhook success.

## Next UI shell items
- Apply theme tokens to buttons/badges across all templates (replace hardcoded `btn-ez` where appropriate).
- Add “collapsed sidebar” (icon-only) option for desktop if needed.
- Add per-user preference storage in DB (future) to sync theme across devices.

## 2026-02-15 — Completed: Phase 6M1 (Launch Checks expansion + static hardening verification)
- Expanded Ops → Launch Checks with WhiteNoise/static verification (middleware + manifest strict).
- Added smoke-level data presence checks (company/client/project/invoice/payment) to confirm end-to-end exercise in the current environment.
- Kept checks lightweight (settings/env + minimal DB existence queries).

## 2026-02-15 — Completed: Phase 6N (Ops Email Diagnostics)
- Added Ops → Email test page (staff-only) to send a real test email and record SENT/FAILED results.
- Failures create an Ops Alert (EMAIL / ERROR) for visibility.
- Launch Checks now include DEFAULT_FROM_EMAIL validation + “recent successful email test” evidence check.

## 2026-02-15 — Completed: Phase 6O.1 (Error page hardening)
- 404/500 templates no longer depend on unstable namespaces; link to stable `home` route.
- Error handlers are defensive to prevent template failures from causing recursive 500s.
- Error pages display Request ID when available for support correlation.

## 2026-02-15 — Completed: Phase 6O.2 (Pagination crash fix)
- Fixed template-time `EmptyPage` exceptions caused by unguarded `previous_page_number()` / `next_page_number()` calls.
- Shared pagination include now guards page-number methods behind `has_previous/has_next`.
- Audit events list pagination hardened the same way.

### Next: Phase 6O — UI reliability polish (mobile + dropdowns)
- Make sidebar + topbar interactions consistent across iOS/Android/desktop (offcanvas + dropdowns + safe areas).
- Audit all navbar dropdowns for Bootstrap-JS independence (match the timer’s deterministic toggle).
- Apply EZ360PM theme tokens to remaining forms/buttons for a more cohesive look.


## 2026-02-15 — Pack: Optional 2FA enforcement + Client email index
- Completed: 2FA enforcement policy change (admin-configurable only).
- Completed: CRM client email index + migration for import/search performance.


## Completed (2026-02-15)

- Phase 6N+ Hotfix: Added `documents:numbering` URL alias to prevent NoReverseMatch on Getting Started.

## 2026-02-15 — Completed: Phase 6O.3 (UI reliability polish — sidebar/company dropdown)

- Sidebar now prevents body scroll when open on mobile (`body.no-scroll`) and closes automatically on nav click.
- Added resize handler to close sidebar/actions when switching to desktop breakpoint.
- Company switcher dropdown is now Bootstrap-independent (deterministic toggle) and themed (`btn-outline-ez`).


## 2026-02-15 — Phase 6O.4: Accessibility polish
- Added skip-to-content link and focus-visible styling.
- Improved keyboard behavior for custom dropdown toggles.

### Phase 6T — Accounts Payable (MVP) ✅
**Goal:** Basic QuickBooks-like bills + vendor tracking with accounting postings.
- Vendors: list/create/edit (company-scoped).
- Bills: draft/create/edit, line items, post (locks), list + status filters.
- Payments: record payments against posted bills.
- Accounting integration: auto-post journal entries for bill posting + bill payments.

### Next (proposed) — Phase 6U
- A/P polish: vendor statements, bill attachments (receipts), recurring bills.
- Payment batching: "Pay bills" screen (select multiple bills), check printing export.
- Aging report for A/P (by vendor, due buckets).


## 2026-02-15 — Next: Payables Phase 7B/7C
- Add A/P Aging report page + export (CSV) and link from Reports.
- Add Bills 'due soon' quick filter and status chips.
- Add Vendor → New Bill shortcut + vendor filter on Bills list.
- Add bill attachment support (S3 private) if required (optional).

### Payables (Accounts Payable) — Next
- Add **Bill attachment downloads** (presigned GET) + optional in-app preview for PDFs/images.
- Add **Vendor 1099 tracking** (vendor type, tax ID storage w/ PII guardrails).
- Add **Recurring bills** (templates + schedule) and bulk posting.
- Expand reporting: cashflow view, spend by vendor/category.

### 2026-02-15 — Phase 7G.1 (Done)
- [x] Fix `/projects/new/` 500: register `catalog.CatalogItem` in Django Admin so `admin:catalog_catalogitem_changelist` resolves.

## 2026-02-15 — Phase 7G1 (Manual skeleton + Help Center routing fix)
**Done:**
- Wired Help Center + Legal URLs into root routing (`helpcenter.urls` now included).
- Updated app top-nav Help icon to open the Help Center.

**Next (corporate-grade hardening & polish):**
1) **Manual + QA**
   - Expand `docs/FEATURE_INVENTORY.md` into full “User Manual + QA Plan”.
   - Add acceptance checks per feature and role.
2) **UX consistency**
   - Enforce `$xx.xx` formatting for all money inputs (forms + templates + admin displays).
   - Normalize select inputs (state dropdown, service selectors) to match Bootstrap styling.
   - Ensure timer dropdown supports project→service→notes and removes redundant client selection.
3) **Catalog as first-class**
   - Add in-app CRUD UI for Catalog Items (Manager/Admin), plus safe search and “add service on the fly”.
4) **Time tracking correctness**
   - Make TimeEntry project-driven (derive client from project; prevent mismatched client/project).
   - Expand approval workflow checks (who can approve, editing rules after approval/billing).
5) **Email deliverability + templates**
   - Standardize transactional email templates (brand header/footer, accessibility, plain-text fallback).
   - Verify SMTP/provider config and bounce handling.
6) **Ops readiness**
   - Add a “production readiness” checklist command (static checks, migrations sanity, required env vars).
   - Add structured logging for request_id across modules.
   - Add backup/restore drill doc + automated DB dump hooks (if not already).
7) **Security posture**
   - Confirm 2FA is optional but fully enforceable via company settings.
   - Ensure rate-limits on login, password reset, and public endpoints.
   - Confirm CSRF/secure cookie flags per environment.

## 2026-02-15 — Phase 7G2 (Corporate polish: Catalog UI + TimeEntry project-driven + money formatting)
**Done:**
- Added in-app **Catalog** (Manager+) with list/search/filter + create/edit/delete.
- Added global money formatting helper (`money_cents` template filter) and money parsing helpers.
- Payment forms now use Decimal-safe dollars→cents conversion and show $ placeholders.
- Time tracking now enforces **project-driven client** (client is derived from project; mismatch blocked).

**Next (Phase 7G3 candidates):**
1) Apply money formatting + $ input UX to **all** money surfaces:
   - Project hourly/flat rates, invoice line items, expenses, bills, COA/journals readouts.
2) Tighten TimeEntry state rules:
   - Lock edits after Approved/Billed; enforce approve/bill permissions; add manager approval UI.
3) Catalog “add on the fly”:
   - From timer + from invoice line item picker.
4) Smoke test expansion:
   - Add invariants for posting idempotency, A/R aging math, partial payments/credits.


## 2026-02-16 — Phase 7H1 (DONE) — Money UX completion + smoke-test alignment

**Done**
- Expenses/Payables/Payments forms migrated to `MoneyCentsField` (cents storage, dollars UI).
- Templates updated for `$` input groups and correct field names.
- Smoke test aligned to project-driven time-entry policy.

**Next (Phase 7H2)**
- Finish money UX + formatting across reporting, dashboards, and any remaining list views/admin columns.
- Expand invariants: document totals, tax totals, balance math; payment/credit invariants; posting idempotency.
- Timer UX: “service on the fly”, persist last project/service selection per user.


## 2026-02-16 — Phase 7H2 (DONE) — Invariants + refund form + money UX polish

**Done**
- Fixed missing `PaymentRefundForm` referenced by `payments.views` (refund UI no longer crashes).
- Added `manage.py ez360_invariants_check` to validate core invoice/payment invariants (totals, paid/balance sanity, succeeded payments bounds).
- Polished money-entry UX in document line item tables (unit price + tax now use `$` input-groups).
- Removed “debug cents” display from Credit Note post confirmation screen.

**Done (Phase 7H3)**
- Expand invariants: credits/credit-notes effective balance, posting idempotency, GL integrity checks.
- Add timer “service on the fly” (create/select CatalogItem directly from the timer dropdown).
- Standardize money formatting in admin list displays and dashboards (use `|money` everywhere).

**Next (Phase 7H4)**
- Finish admin money formatting (Expenses, Payables, Credit Notes, Refunds) and remove any remaining raw cents UI.
- Add stronger invariants: credit ledger vs applications, refunds vs paid snapshots, posting idempotency scan.
- Timer UX: persist last project/service/note and add quick link to manage Catalog.

## 2026-02-16 — Phase 7H4 (DONE) — Admin money polish + refund/journal invariants + timer link

**Done**
- Completed admin money formatting across operator-critical models (no raw cents in admin list displays).
- Expanded `ez360_invariants_check` for refund sanity and JournalEntry provenance checks.
- Added “Manage catalog services” quick link in timer UI for Manager+.

**Next (Phase 7H5)**
- Expand invariants to cover client credit ledger vs rollup, credit applications sanity, and net-payment math (amount - refunded).
- Fix any structural issues inside `ez360_invariants_check` and make output reliable (no indentation/flow bugs).
- Add idempotency cross-checks where possible (journal uniqueness / provenance).


## 2026-02-16 — Phase 7H5 (DONE) — Invariants suite reliability + client credit sanity + journal balance checks

**Done**
- Rewrote `manage.py ez360_invariants_check` for correctness and readability:
  - Invoice totals + paid/balance sanity
  - Net payments = amount - refunded checks
  - Client credit ledger sum vs `Client.credit_cents` rollup warnings
  - Credit application integrity checks (positive cents; invoice/company/client matching)
  - Payment refunds sanity checks
  - JournalEntry balance checks (debits == credits) + provenance enforcement
- Added `--quiet` option for CI-style runs.

**Next**
- Extend invariants to validate:
  - per-invoice applied credits never exceed available credit at time of application (requires snapshotting policy or sequential rebuild)
  - posting idempotency mapping across invoices/payments/expenses (source_type/source_id coverage audit)
- Timer persistence: remember last project/service/note per employee (DB-backed).

### Phase 7H9 — Readiness Gate + Ops UI (DONE)
- Add `ez360_readiness_check` management command (env/db/migrations/storage/email) and surface it in Ops → Checks (staff-only).
- Capture output for launch evidence and reduce reliance on CLI access.

### Phase 7H10 — Email Professionalization + Help Context (NEXT)
- Add branded transactional email base templates (HTML + text) and standard subjects.
- Add “Help” contextual links on key pages (Invoices, Payments, Bills, Time) to reduce support burden.
- Add minimal email “preview” dev endpoint (staff-only) for template QA.

## 2026-02-16 — Phase 7H11 (DONE)
- Ops Checks UI: added Company picker, Quiet + Fail-fast options.
- Added OpsCheckRun history model + admin. Ops Checks page now shows recent runs with output.
- Ops Checks now persists run history for launch evidence (best-effort).

## 2026-02-16 — Phase 7H12 (NEXT)
- Posting provenance audit: ensure every auto-posting source sets JournalEntry.source_type/source_id.
- Ops Checks: add “pin run to release” (link to ReleaseNote) and export evidence bundle.
- Email professionalization: consistent subjects + reply-to + list headers, and template lint.

## 2026-02-16 — Phase 7H12 (DONE)
- Timer UX: added "Open selected project" shortcut in timer dropdown and timer page.
- Small corporate UX polish in time workflow.

## 2026-02-16 — Phase 7H13 (DONE)
- Money display unification: legacy `|cents_to_dollars` now matches corporate `$x,xxx.xx` output.
- Preferred currency filter is `|money` and key surfaces were updated to use it.

## 2026-02-16 — Phase 7H14 (NEXT)
- Email polish: standardize all transactional email subjects, add plain-text fallbacks where missing, and ensure consistent support contact and company branding.
- Help Center content: fill core articles (Getting Started, Time Tracking, Invoices & Payments, Bills & AP, Reports) with concrete, role-based instructions.
- Expand Ops Checks: add download/export of run output for launch evidence (CSV/text) and cap stored output size with truncation notice.

## 2026-02-16 — Phase 7H15 (DONE)
- Ops dashboard seat-limit crash fixed (computed seat limits via `seats_limit_for`).

## 2026-02-16 — Phase 7H16 (DONE)
- Recurring bills list: load `money` filter and add contextual Help link.

## 2026-02-16 — Phase 7H17 (DONE)
- Fixed Ops dashboard NoReverseMatch by updating Ops company routes to use UUID converters.
- Ops company detail/timeline/resync endpoints now accept `<uuid:company_id>`.

## Next (Phase 7H18)
- Template sweep: ensure any template using `|money` loads `{% load money %}` (prevent regressions).
- Expand Help Center Accounting content (Bills/Recurring Bills/Payments workflows).
- Ops: add company ID display/copy button and improve company search/filtering.

## 2026-02-16 — Phase 7H19
**DONE**
- Fix Ops Checks indentation error (ops/views.py) blocking app startup.
- Improve template sanity check coverage for money filters.

**NEXT**
- Continue template sanity sweeps (reverse/url/tag loads) and add checks for other common tag libraries.

## 2026-02-16 — Phase 7H22
**DONE**
- Ops Checks: added **Run all** option (runs all checks; skips Smoke Test when no company selected).
- App navigation: added **Help Center** link in sidebar.
- Help Center: expanded home “topic tiles” for core workflows.

**NEXT (Phase 7H23)**
- Help Center: deepen each article with role-based step-by-step instructions (time approvals, invoicing, credits/refunds, bills/recurring bills) + screenshots placeholders.
- Ops Checks: add one-click “Run recommended” preset (launch evidence default set).
- Template sanity: also warn on `{% url %}` without quotes, and missing `{% load humanize %}` where used.


## 2026-02-17 — Phase 8K (DONE)
Ops System Status:
- Added Ops → System status (staff-only) to show environment/runtime details and **pending migrations**.
- Linked from Ops dashboard.

### Next (Phase 8L)
Launch polish + verification:
- Add "Release checklist" runbook page and export (PDF/CSV) for go-live.
- Add post-deploy verification checklist (healthz/version, pending migrations=0, admin access, email, Stripe webhooks).
- Review remaining rough edges (forms, empty-states, permissions) and close dead ends.

- [x] **8L** Timer dropdown completion (project/service/notes) + Clients list shows company name (2026-02-17)
- [x] **8M** Post-deploy smoke tests (Ops page + management command) + fixed context_processors syntax regression (2026-02-17)
- [x] **8N** Comped subscriptions + discount metadata (staff overrides + admin fields) (2026-02-17)
- [x] **8O** End-to-end go-live runbook export + final launch gate pass (PDF/CSV) + final UX punchlist (2026-02-17)

## 2026-02-17 — Phase 8O (DONE)
Go-live runbook export + launch verification bundle:
- Added Ops → **Go-live runbook** page aggregating Launch Gate, pending migrations, and manual verification checklist.
- Added CSV export (`/ops/runbook/export.csv`) for spreadsheet evidence.
- Added PDF export (`/ops/runbook/export.pdf`) using **ReportLab** (no WeasyPrint system deps).
- Linked from Ops dashboard for one-click access during launch.


### Phase 8P — Maintenance Mode (Ops safety switch)
- DONE: Ops SiteConfig maintenance mode toggle + 503 maintenance page middleware.

### Phase 8Q — List UX Counts (DONE)
- DONE: Clients list now shows **range + total** (e.g., “Showing 1–25 of 83 clients”).
- DONE: Pagination footer (multi-page lists) now shows **page + range + total**.

### Phase 8R — Ops Console + Runbook Hotfix (DONE)
- DONE: Enabled `django.contrib.humanize` so Ops Runbook templates can safely `{% load humanize %}`.
- DONE: Ops Console toolbar overflow fix (wrap on desktop, horizontal scroll on smaller screens).

### Phase 8S — Bank Feeds Scaffold (DONE)
- Added **Bank feeds** integration scaffold under Integrations (Professional+).
- Added models: `BankConnection`, `BankAccount`, `BankTransaction`.
- Added admin registration and a user-facing settings page (`/integrations/banking/`).
- Added env toggles: `PLAID_ENABLED`, `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`.
- Notes:
  - This pack is intentionally **scaffold-only** (no Plaid SDK dependency yet).
  - Next pack will implement secure Link flow + transaction sync + expense creation.

### Phase 8S2 — V1 Launch Manual + End-to-End QA Punchlist (DONE)
- DONE: Published **User Manual PDF** at `/static/docs/ez360pm_user_manual.pdf` and linked it from Help Center.
- DONE: Added **Ops → QA Punchlist** (staff-only) to log bugs/dead-ends found during guided QA.
- DONE: Added Ops Dashboard metric/badge for open QA issues.

### Phase 8Y — V1 Launch Polish + QA Fix Sprint (DONE)
- Added a **staff-only “Report issue”** shortcut button (bug icon) in the app topbar.
  - Pre-fills QA form with the current page URL and an automatic area guess.
  - Preserves tenant context (active company) when available.
- QA issue form now supports safe querystring prefill (`related_url`, `area`, `company`).

## 2026-02-17 — Phase 9 (DONE)
Bank reconciliation hardening:
- Added **Reconciliation Periods** (create period windows).
- Added period **Detail** view with diffs: bank outflow vs expense totals, matched/unmatched counts.
- Added **Lock / Undo lock** workflow with snapshot fields for audit clarity.
- Added **CSV export** for the reconciliation window.

### Next: Phase 10 — Reconciliation + Reporting polish
- Improve matching UI (link/unlink from the reconciliation screen).
- Add PDF reconciliation export (WeasyPrint when available).
- Add multi-account reconciliation totals and better inflow/outflow handling.

-- [x] Phase 8S: Fix subscription gating leaks
  - [x] Gate Expenses module to Professional+
  - [x] Gate Time Approval workflow to Professional+ (and prevent Starter dead-ends)

- [x] Phase 8T: Hide unavailable modules in sidebar navigation
  - [x] Expenses hidden unless Professional+
  - [x] Accounting hidden unless Professional+
  - [x] Integrations (Dropbox) hidden unless Premium

- [x] Phase 8U: Tiered dashboard widgets
  - [x] Starter: hide Expenses KPI + Payables card
  - [x] Professional+: show Expenses KPI + Payables summary
  - [x] Premium: add Insights card (trends + overdue alerts + Dropbox status) for managers

- [x] Phase 8V: Premium custom dashboards (v1)
  - [x] Per-company, per-role widget layout storage (`core.DashboardLayout`)
  - [x] Premium Manager+ “Customize Dashboard” page (enable/disable, column, order)
  - [x] Dashboard rendering refactored to widget/include layout driven by stored layout

- [DONE] Phase 8T — Bank Feeds (Plaid) real integration: Link flow + token exchange + accounts + sync + create expense.
- [DONE] Phase 8U — Bank rules & categorization: rule-based suggestions + ignore/transfer triage + safe expense creation.
- [DONE] Phase 8X — Bank review queue + duplicate prevention: bulk actions, matching heuristics, reconciliation view.
  - [x] Review queue page with status/account filters + pagination
  - [x] Bulk actions: Ignore / Transfer / Create Expense / Link Suggested
  - [x] Conservative duplicate suggestion heuristic (same amount + date window + merchant match)
  - [x] Reconciliation summary view (windowed counts per status + per account)

### Hotfixes
- [DONE] Dropdown styling sweep — normalize select widgets (CSS + client-side fallback for missing `form-select`).

- [DONE] Phase 8W — Plaid readiness hardening (ship-safe)
  - [x] Only load Plaid Link JS when Bank Feeds are enabled + configured
  - [x] Bank Feeds UI note clarifies sandbox vs production and Plaid verification expectations

- [DONE] Phase 8U — Bank feed rules + transaction triage
  - [x] Added `integrations.BankRule` (per-company) with priority ordering and actions (suggest/ignore/transfer/auto-create expense)
  - [x] Enhanced `integrations.BankTransaction` with status + suggestions + linked expense + applied rule
  - [x] Auto-apply rules after bank sync; manual “Apply rules” button
  - [x] Banking UI shows status/suggestions and supports Ignore/Transfer/Create expense
  - [x] Rule management UI (list/create/edit/delete) gated to Professional + Admin+
  - [x] Admin registrations for BankRule and improved BankTransaction admin



## 2026-02-17 — Phase 9 (IN PROGRESS) — Reconciliation + Hardening QA

We are entering **Phase 9** with a strict **feature-by-feature QA + fix loop**.

- QA plan and execution order: `docs/QA_PLAN.md`
- As each feature is validated, we will:
  - expand `docs/FEATURE_INVENTORY.md` with real “how it works” steps + acceptance checks
  - log outcomes in the QA Ledger
  - apply Fix Packs (`P9-*`) for any failures
  - update `docs/MEMORY.md` with findings and decisions

### Phase 9 focus areas
- Company isolation + role enforcement
- Timer dropdown + time state machine integrity
- Invoices/payments correctness and immutability
- Accounting posting idempotency + reconciliation views
- Dead links, help/legal completeness, and launch gating

### Next up
- [DONE] P9-UI1: UI consistency sweep + boot fixes
  - Fix Integrations import break (`get_active_employee` alias)
  - Shorten Ops QA index names (cross-DB safe) + rename migration
  - Standardize remaining straggler pages to `card shadow-sm`

- [DONE] P9-UI2: UI baseline hardening + bundle hygiene
  - Standardized **card styling** at the CSS level so every card matches even if a template forgot `shadow-sm`.
  - Standardized **dropdown menu styling** (radius/shadow/spacing) so action menus feel consistent.
  - Removed accidental shipped artifacts (`.venv/`, `__pycache__/`, `*.pyc`, `_insert_phase9_views.txt`) and added `.gitignore`.

- Start QA Feature 0: Access + Company Context + Roles (launch blockers)


### DONE — 2026-02-18
- **P9-DOC-LOGO-SAFE:** Prevent document pages from 500ing when company logo storage is misconfigured; added safe media URL helper and template fallbacks.

### P9-LEGAL-PAGES (DONE)
- Ensure all public legal routes render successfully in production.
- Templates present for: terms, privacy, cookies, acceptable use, security, refund policy.
- Smoke tests added in helpcenter app.

### P9-LEGAL-POLICIES (DONE)
- Replaced placeholder legal templates with full Terms/Privacy/Cookies/Security/AUP/Refund Policy content.
- Added `legal_last_updated` context to standardize the “Last updated” date.


## Phase 9 – P9-SCANNER-SHIELD

- [x] P9-TESTING-GUIDE — Add `docs/TESTING.md` as canonical test workflow and must-pass targets.
- Added ScannerShieldMiddleware to short-circuit common bot/scanner endpoints (e.g. /webhook-test, /.env) and reduce log noise.
- Added core tests for blocked probe paths.
- Added helpcenter to INSTALLED_APPS to ensure legal/help pages render in production.

## Phase 9 – P9-OPS-HEALTH-ENDPOINTS

- [x] Add `GET /health/` (safe public healthcheck) and `GET /health/details/` (token-protected; disabled unless configured).
- [x] Document the production baseline + launch gate checklist.
- [x] Add env var docs for `HEALTHCHECK_TOKEN`.

## Phase 9 (QA) — QA1 Manual Checklist + Seed (DONE)
- Added docs/MANUAL_QA_CHECKLIST.md and local seed_qa command.
- Next: QA2 — permission matrix verification + billing trial/seat flows end-to-end + PDF parity spot-checks on staging/prod.

### DONE — 2026-02-18
- **P9-FOOTER-IN-APP:** Logged-in pages now show the same footer legal links as the public site (shared footer partial included in `base_app.html`).

### DONE — 2026-02-19
- **P9-DASHBOARD-NOTES-LAYOUT:** Simplified the dashboard right rail (Quick actions + Getting started until complete + Quick notes).
- **P9-BILLING-TRIAL-SETTINGS:** Trial length is now editable in-app (Ops → Alert routing) via `billing_trial_days`, used for Stripe subscription checkout (card-first trial). Added ops signup/conversion notification emails.
  - Added Notes module (`notes` app) and `/notes/` page for call/intake capture.
  - Moved active company display under the sidebar company dropdown.
  - Dashboard header now shows user name + role.


### DONE — 2026-02-21
- **P9-OPS-CENTER-PACK3:** Ops Center company controls + audit trail.
  - Added tenant suspension fields + middleware + suspended landing page.
  - Added force-logout control (User.force_logout_at + middleware + auth_time session marker).
  - Ops company detail: tabbed executive console (Overview/Billing/Users/Activity/Ops audit).
  - Added OpsActionLog for platform-level staff action logging.Added OpsActionLog for platform-level staff action logging.

- **P9-OPS-CENTER-PACK4:** Billing Control queue (Stripe action approvals + run) + Support Mode guardrails.
  - Queued Stripe action model + UI (approve/run/cancel) and company billing control panel.
  - Support mode now requires reason + presets + duration clamp.

- **P9-OPS-CENTER-PACK6:** Safety confirmations + support banner polish.
  - Typed confirmations for high-impact ops actions (suspend/reactivate/force logout + Stripe approve/run).
  - Support-mode banner shows company name and links to Company 360.


## 2026-02-21 — Ops Center Pack 8 (DONE)

- Added `/ops/reports/` operational reports page (MRR/ARR, churn, trials, webhook health, payment failures, alerts).

## 2026-02-21 — Ops Center Pack 10 (DONE)

- Added **Stripe-authoritative daily revenue snapshots**:
  - `ops.PlatformRevenueSnapshot` + daily command `ez360_snapshot_platform_revenue`.
  - `ops.CompanyLifecycleEvent` foundation for accurate churn/conversion analytics.
- Updated `/ops/reports/` to consume snapshots + begin lifecycle-based growth metrics.
## 2026-02-21 — Ops Center Pack 11 (DONE)

- Wired **subscription lifecycle events** from Stripe webhooks (best-effort):
  - Trial started / converted
  - Subscription started / canceled / reactivated
- Added `billing.CompanySubscription.last_stripe_event_at` as a webhook freshness marker.
- Added mirror drift alerting:
  - `ez360_stripe_desync_scan` command (default 48h)
  - Daily revenue snapshot command now emits WARN alerts if mirror is stale.

## 2026-02-21 — Ops Center Pack 12 (DONE)

- SiteConfig now controls Stripe mirror drift:
  - `stripe_mirror_stale_after_hours`
  - `stripe_mirror_stale_alert_level`
- SiteConfig can enforce 2FA for critical ops actions (`ops_require_2fa_for_critical_actions`).
- Ops Reports includes a new Stripe health panel (last webhook + drift examples).
- Critical ops actions (suspend/reactivate, force logout, Stripe action approve/run/cancel) are blocked if 2FA enforcement is enabled and the session is not 2FA-verified.

### Next

- Ops Reports: add lifecycle charts (trials → conversions, churn, reactivations) using `CompanyLifecycleEvent`.
- Ops Reports: add lightweight visualizations (sparklines) for MRR and lifecycle funnels.
- Ops Billing: add “reconcile now” action to force a subscription sync from Stripe for a single company.
- Ops Governance: consider 4-eyes approval for company suspension (optional) once early customers arrive.


### Pack 13 — Ops RBAC + governance (DONE)
- Ops role assignments + Access UI
- Role gates for critical actions
- Fix missing auth decorator on company detail

### Pack 14 — Lifecycle funnel + Webhook Health + Tenant Risk (DONE)
- Ops Reports: upgraded lifecycle funnel (30d) with conversion/churn rates, reactivations, net growth, and a “recent lifecycle events” feed (CompanyLifecycleEvent-backed).
- Ops Webhook Health page: new `/ops/webhooks/` dashboard with delivery totals, last event, top event types, and recent handler failures, plus Stripe mirror drift panel.
- Companies grid: added per-tenant risk score (0–100) with flags (past_due, mirror_stale, payment_failed_14d, canceling, trial_ends_7d, suspended) for fast triage.

### Next (Pack 15)
- Add configurable risk scoring weights + thresholds to SiteConfig (operator-tunable).
- Add “webhook stale” alert thresholds and a daily webhook health snapshot.
- Add basic lifecycle charts (weekly buckets) and MRR sparkline rendering (server-side).

## 2026-02-21 — Ops Center Pack 15 (DONE)

- Tunable tenant risk scoring via SiteConfig + Ops UI.


## 2026-02-21 — Ops Center Pack 16
- DONE: Pack 16 — Risk drill-down on Company 360 + per-operator saved Company presets.

## 2026-02-22 — Ops Center Pack 17
- DONE: Preset management UI (rename, activate/deactivate, set default, delete).
- DONE: Daily Company Risk Snapshots + 30-day risk trend table on Company 360.
- DONE: Two-person approval toggle for Stripe ops actions (requester cannot approve/run).

## 2026-02-22 — Ops Center Pack 18C (DONE)

- DONE: Executive-grade Ops Center branding (light) and **sectioned navigation layout**.
- DONE: Left sidebar navigation grouped into operational domains (Dashboard / Tenants / Billing Ops / Security Ops / System Settings), with responsive mobile fallback.
- DONE: Ops shell status strip (environment, Stripe mode, open alerts, support mode) for “console” visibility.

- [x] Pack 18C3: Ops header Tools dropdown + on-demand snapshot/desync scan actions (operator console polish)
- [x] Pack 18C4: Expand Ops Tools (readiness/smoke/backup quick actions) + recent ops actions mini-feed; fix ops_launch_checks bug

## 2026-02-22 — Ops Center Pack 19 (DONE)

- [x] Add **Ops → Activity** (`/ops/activity/`) as a unified executive audit feed:
  - Ops actions (filterable + CSV export)
  - Checks evidence (filterable)
- [x] Add Activity to sidebar and Ops Tools quick links.
- [x] Fix dropdown URL to use `ops:webhook_health`.

## 2026-02-22 — Ops Center Pack 20 (DONE)

- [x] Add **Company workspace** card on Company 360 with deep links into tenant UI (Dashboard/Clients/Projects/Invoices/Payments/Time).
- [x] Enforce **Support Mode scoping** for tenant workspace navigation (must be active for the target company).
- [x] Add `/ops/companies/<uuid>/jump/<dest>/` to set active company + redirect + log `ops.company_jump`.
- [x] Extend Ops Activity feed to include **Stripe actions** (OpsStripeAction) + filter/search.
- [x] Extend Activity CSV export to support **Stripe actions** when tab=stripe.

### Next (Ops polish)
- [ ] Add a persistent **Support Mode banner** in tenant UI (outside Ops) showing "Viewing as Support" + company name + expiry + exit button.
- [ ] Add dedicated **Stripe action detail** view from Activity list (drill-down to payload + resolution).

## 2026-02-22 — Pack 21 (DONE) — Executive Hardening: Monitoring & Observability

- [x] Production-grade **/health/** endpoint with DB/cache/S3/Stripe checks (structured JSON + ok/degraded/error + 200/503).
- [x] Token-protected **/health/details/** endpoint (requires `HEALTHCHECK_TOKEN`) with per-component error summaries.
- [x] Email delivery observability:
  - [x] `OutboundEmailLog` model + migration
  - [x] logging wired into `core.email_utils.send_templated_email()`
  - [x] Ops → Email health dashboard (`/ops/email/`)
- [x] Ops top strip upgraded with executive telemetry (Webhooks / Email / Snapshot / Mirror drift).
- [x] Sentry hardening:
  - [x] Sentry context middleware (user + company)
  - [x] Ops Reports Sentry panel + optional dashboard link env var.
- [x] Slow-request guardrail enabled (PerformanceLoggingMiddleware active with prod defaults).

## Pack 22 (DONE) — Backup & Recovery Gate

- [x] Automated daily DB backup verification (`ez360_verify_backups`) wired into `ez360_run_ops_checks_daily`.
- [x] Backup integrity test (best-effort):
  - local: verifies recorded path exists and is readable (gzip sniff)
  - s3: `head_object` check for bucket/key + size consistency
- [x] Restore drill command (`ez360_restore_drill`) prints operator checklist and can record PASS/FAIL evidence.
- [x] Ops status strip now includes **Backup health** chip with last successful backup timestamp.
- [x] Ops → Backups page includes automated verification panel + output.
- [x] Backup verification failure creates an Ops Alert (no silent recoverability drift).

