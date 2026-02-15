from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.db.connection import connect
from app.sync.http import ApiClient


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class SyncResult:
    pulled: int = 0
    pushed: int = 0
    errors: list[str] | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class SyncEngine:
    """
    Minimal v1 skeleton:
    - license_check(company_id)
    - register_device(company_id, device_id)
    - pull since cursor
    - push outbox_changes
    - apply pulled entities locally (core models only)
    """

    def __init__(self, api: ApiClient):
        self.api = api

    def license_check(self, company_id: str) -> dict[str, Any]:
        return self.api.post("/api/v1/sync/license/check/", {"company_id": company_id, "client_time": _utc_now_iso()})

    def register_device(self, company_id: str, device_id: str, name: str = "Windows Desktop") -> dict[str, Any]:
        payload = {"company_id": company_id, "device_id": device_id, "platform": "windows", "name": name}
        return self.api.post("/api/v1/sync/devices/register/", payload)

    def pull(self, company_id: str, since_iso: str) -> dict[str, Any]:
        return self.api.get("/api/v1/sync/pull/", {"company_id": company_id, "since": since_iso, "limit": 5000})

    def push(self, company_id: str, device_id: str, changes: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        payload = {"company_id": company_id, "device_id": device_id, "client_time": _utc_now_iso(), "changes": changes}
        return self.api.post("/api/v1/sync/push/", payload)

    def run_once(self, company_id: str, device_id: str) -> SyncResult:
        res = SyncResult()
        conn = connect()
        try:
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('last_sync_since','1970-01-01T00:00:00Z')")
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('last_sync_at','')")
            conn.commit()

            since = conn.execute("SELECT value FROM meta WHERE key='last_sync_since'").fetchone()["value"] or "1970-01-01T00:00:00Z"

            # 1) Pull
            pulled_payload = self.pull(company_id, since)
            server_time = str(pulled_payload.get("server_time") or _utc_now_iso())
            next_since = str(pulled_payload.get("next_since") or server_time)

            entities = pulled_payload.get("entities") or {}
            pulled_count = 0
            for model_label, rows in entities.items():
                pulled_count += self._apply_entities(conn, model_label, rows or [])
            res.pulled = pulled_count

            # 2) Push outbox
            outbox = conn.execute(
                "SELECT id, model, object_id, payload_json FROM outbox_changes WHERE company_id=? ORDER BY created_at ASC LIMIT 200",
                [company_id],
            ).fetchall()

            if outbox:
                changes: dict[str, list[dict[str, Any]]] = {}
                for row in outbox:
                    model = row["model"]
                    payload = json.loads(row["payload_json"])
                    changes.setdefault(model, []).append(payload)

                push_result = self.push(company_id, device_id, changes)
                results = push_result.get("results") or {}

                applied_ids: set[str] = set()
                for model_label, model_results in results.items():
                    for item in model_results or []:
                        if item.get("status") in {"applied", "conflict_overwritten"}:
                            applied_ids.add(str(item.get("id") or ""))

                if applied_ids:
                    conn.executemany("DELETE FROM outbox_changes WHERE object_id=?", [(i,) for i in applied_ids if i])

                res.pushed = sum(len(v or []) for v in results.values())

            # 3) Update cursors
            conn.execute("UPDATE meta SET value=? WHERE key='last_sync_since'", [next_since])
            conn.execute("UPDATE meta SET value=? WHERE key='last_sync_at'", [server_time])
            conn.commit()
            return res
        finally:
            conn.close()

    def _apply_entities(self, conn, model_label: str, rows: list[dict[str, Any]]) -> int:
        """
        Minimal mapping for core tables. Extend as we add modules.
        Expects server payload to include fields compatible with table columns.
        """
        if not rows:
            return 0

        mapping = {
            "companies.Company": (
                "companies",
                [
                    "id","name","created_at","updated_at","revision","deleted_at","is_active",
                    "email_from_name","email_from_address","address1","address2","city","state","zip_code"
                ],
            ),
            "companies.EmployeeProfile": (
                "employee_profiles",
                [
                    "id","company_id","user_id","display_name","username_public","role","is_active",
                    "hired_at","terminated_at","hourly_rate","can_view_company_financials","can_approve_time",
                    "created_at","updated_at","revision","deleted_at"
                ],
            ),
            "crm.Client": (
                "clients",
                [
                    "id","company_id","first_name","last_name","company_name","email","internal_note",
                    "address1","address2","city","state","zip_code",
                    "credit_cents","outstanding_cents",
                    "created_at","updated_at","revision","deleted_at"
                ],
            ),
            "projects.Project": (
                "projects",
                [
                    "id","company_id","client_id","project_number","name","description","date_received","due_date",
                    "billing_type","flat_fee_cents","hourly_rate_cents","estimated_minutes","assigned_to_employee_id",
                    "is_active","created_at","updated_at","revision","deleted_at"
                ],
            ),
            "documents.Document": (
                "documents",
                [
                    "id","company_id","doc_type","client_id","created_by_employee_id","number","title","description",
                    "issue_date","due_date","valid_until","status",
                    "subtotal_cents","tax_cents","total_cents","amount_paid_cents","balance_due_cents",
                    "notes","created_at","updated_at","revision","deleted_at"
                ],
            ),
            "documents.DocumentLineItem": (
                "document_line_items",
                [
                    "id","document_id","sort_order","catalog_item_id","name","description","qty","unit_price_cents",
                    "line_subtotal_cents","tax_cents","line_total_cents","is_taxable",
                    "created_at","updated_at","revision","deleted_at"
                ],
            ),
            "timetracking.TimeEntry": (
                "time_entries",
                [
                    "id","company_id","employee_id","client_id","project_id","started_at","ended_at","duration_minutes",
                    "billable","note","status","approved_by_employee_id","approved_at",
                    "created_at","updated_at","revision","deleted_at"
                ],
            ),
        }

        if model_label not in mapping:
            return 0

        table, cols = mapping[model_label]
        placeholders = ",".join(["?"] * len(cols))
        collist = ",".join(cols)
        update_set = ",".join([f"{c}=excluded.{c}" for c in cols if c != "id"])

        count = 0
        for r in rows:
            values = [r.get(c) for c in cols]
            sql = f"INSERT INTO {table} ({collist}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {update_set}"
            conn.execute(sql, values)
            count += 1
        conn.commit()
        return count
