from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db import connection
from django.test.utils import CaptureQueriesContext

from companies.models import Company, EmployeeProfile
from documents.models import Document, DocumentType, DocumentStatus
from timetracking.models import TimeEntry, TimeStatus


class Command(BaseCommand):
    """Phase 3W: lightweight performance sanity checks.

    This command is intentionally simple and safe to run locally or on a staging DB.
    It executes the same *core* list-page querysets used by the UI and reports:
      - total elapsed time
      - SQL query count
      - slowest queries (top N)

    Examples:
      python manage.py perf_check --company-id 1
      python manage.py perf_check --company-id 1 --employee-id 12
      python manage.py perf_check --company-id 1 --doc-type invoice --doc-status sent
      python manage.py perf_check --company-id 1 --time-status submitted
    """

    help = "Run lightweight ORM perf checks for common list queries (Phase 3W)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--employee-id", type=int, default=None)

        parser.add_argument("--doc-type", type=str, default="invoice", choices=["invoice", "estimate", "proposal"])
        parser.add_argument("--doc-status", type=str, default="", help="Optional document status filter")

        parser.add_argument("--time-status", type=str, default="", help="Optional time status filter")
        parser.add_argument("--billable", type=str, default="", choices=["", "0", "1"], help="Optional billable filter")

        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--top", type=int, default=5, help="How many slowest SQL statements to show")

    def _print_queries(self, ctx: CaptureQueriesContext, top: int):
        queries = list(ctx.captured_queries)
        self.stdout.write(f"SQL queries: {len(queries)}")
        ranked = []
        for q in queries:
            raw = q.get("time")
            try:
                ms = float(raw) * 1000.0
            except Exception:
                ms = 0.0
            sql = (q.get("sql") or "").strip().replace("\n", " ")
            ranked.append((ms, sql))
        ranked.sort(key=lambda x: x[0], reverse=True)
        for ms, sql in ranked[: max(1, top)]:
            self.stdout.write(self.style.WARNING(f"  {ms:.1f}ms  {sql[:900]}"))

    def handle(self, *args, **options):
        company_id = options["company_id"]
        employee_id = options.get("employee_id")
        doc_type = options["doc_type"]
        doc_status = (options.get("doc_status") or "").strip()
        time_status = (options.get("time_status") or "").strip()
        billable = (options.get("billable") or "").strip()
        limit = int(options["limit"])
        top = int(options["top"])

        company = Company.objects.get(pk=company_id)
        employee = EmployeeProfile.objects.filter(pk=employee_id, company=company).first() if employee_id else None

        self.stdout.write(self.style.MIGRATE_HEADING("Phase 3W · perf_check"))
        self.stdout.write(f"Company: {company.id} · {company.name}")
        if employee:
            self.stdout.write(f"Employee: {employee.id} · {employee.user.email} · role={employee.role}")

        # -------------------------
        # Documents list queryset
        # -------------------------
        self.stdout.write("\n[Documents list queryset]")
        qs_doc = (
            Document.objects.filter(company=company, doc_type=doc_type, deleted_at__isnull=True)
            .select_related("client", "project")
            .order_by("-created_at")
        )
        if doc_status:
            # Validate against choices (best effort)
            allowed = {c[0] for c in DocumentStatus.choices}
            if doc_status not in allowed:
                self.stdout.write(self.style.ERROR(f"Invalid --doc-status '{doc_status}'. Allowed: {sorted(allowed)}"))
                return
            qs_doc = qs_doc.filter(status=doc_status)

        with CaptureQueriesContext(connection) as ctx:
            t0 = time.perf_counter()
            _ = list(qs_doc[:limit])
            dt = (time.perf_counter() - t0) * 1000.0
        self.stdout.write(f"Elapsed: {dt:.1f}ms")
        self._print_queries(ctx, top)

        # -------------------------
        # Time entries list queryset
        # -------------------------
        self.stdout.write("\n[Time entries list queryset]")
        qs_time = (
            TimeEntry.objects.filter(company=company, deleted_at__isnull=True)
            .select_related("client", "project", "employee", "approved_by")
            .prefetch_related("services")
            .order_by("-started_at", "-created_at")
        )
        if employee:
            # Mimic staff scoping (best-effort) if employee specified.
            qs_time = qs_time.filter(employee=employee)
        if time_status:
            allowed = {c[0] for c in TimeStatus.choices}
            if time_status not in allowed:
                self.stdout.write(self.style.ERROR(f"Invalid --time-status '{time_status}'. Allowed: {sorted(allowed)}"))
                return
            qs_time = qs_time.filter(status=time_status)
        if billable in {"0", "1"}:
            qs_time = qs_time.filter(billable=(billable == "1"))

        with CaptureQueriesContext(connection) as ctx2:
            t0 = time.perf_counter()
            _ = list(qs_time[:limit])
            dt2 = (time.perf_counter() - t0) * 1000.0
        self.stdout.write(f"Elapsed: {dt2:.1f}ms")
        self._print_queries(ctx2, top)

        self.stdout.write(self.style.SUCCESS("\nDone."))
