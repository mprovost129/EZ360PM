from __future__ import annotations

import uuid
from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QLabel,
    QPushButton,
    QMessageBox,
)

from app.auth.token_store import load_tokens
from app.settings.local_settings import load_settings
from app.sync.http import ApiClient
from app.sync.client import SyncEngine
from app.db.schema import apply_schema
from app.utils.paths import get_db_path
from app.db.connection import connect


class AppShell(QMainWindow):
    def __init__(self, schema_sql: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EZ360PM Desktop")
        self.resize(1200, 750)

        self.settings = load_settings()
        self.tokens = load_tokens()
        self.api = ApiClient(self.settings.base_url, self.tokens)
        self.sync = SyncEngine(self.api)

        # Ensure DB schema exists
        apply_schema(schema_sql, get_db_path())

        self.device_id = self._ensure_device_id()

        # UI
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout()
        central.setLayout(root)

        # Sidebar (static)
        self.sidebar = QListWidget()
        self.sidebar.addItems([
            "Dashboard",
            "Clients",
            "Proposals",
            "Estimates",
            "Invoices",
            "Payments",
            "Expenses",
            "Projects",
            "Time Tracking",
            "Accounting",
            "Reports",
            "Settings",
        ])
        self.sidebar.setFixedWidth(220)

        # Main area
        main = QVBoxLayout()

        topbar = QHBoxLayout()
        self.lbl_company = QLabel("Company: (not selected)")
        self.lbl_company.setStyleSheet("font-weight: 600;")
        topbar.addWidget(self.lbl_company)

        topbar.addStretch(1)

        self.btn_sync = QPushButton("Sync now")
        self.btn_sync.clicked.connect(self.on_sync_clicked)
        topbar.addWidget(self.btn_sync)

        self.lbl_status = QLabel("Ready")
        topbar.addWidget(self.lbl_status)

        main.addLayout(topbar)

        self.content = QLabel(
            "Select a module from the left sidebar.\n\n"
            "(This is the skeleton shell — next packs will add pages.)"
        )
        self.content.setStyleSheet("padding: 18px;")
        main.addWidget(self.content, 1)

        root.addWidget(self.sidebar)
        root.addLayout(main, 1)

        # Periodic sync timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._sync_tick)
        self.timer.start(max(10, int(self.settings.sync_interval_seconds)) * 1000)

        self._bootstrap_company()

    def _ensure_device_id(self) -> str:
        conn = connect()
        try:
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('device_id','')")
            row = conn.execute("SELECT value FROM meta WHERE key='device_id'").fetchone()
            device_id = (row["value"] or "").strip()
            if not device_id:
                device_id = str(uuid.uuid4())
                conn.execute("UPDATE meta SET value=? WHERE key='device_id'", [device_id])
                conn.commit()
            return device_id
        finally:
            conn.close()

    def _bootstrap_company(self):
        company_id = (self.settings.active_company_id or "").strip()
        if not company_id:
            self.lbl_company.setText("Company: (set active_company_id in settings.json)")
            return

        self.lbl_company.setText(f"Company: {company_id}")

        # register device best-effort
        try:
            self.sync.register_device(company_id, self.device_id)
        except Exception:
            pass

    def _sync_tick(self):
        if not self.settings.sync_enabled:
            return
        company_id = (self.settings.active_company_id or "").strip()
        if not company_id:
            return
        try:
            self._run_sync(company_id)
        except Exception:
            # periodic sync is best-effort
            pass

    def on_sync_clicked(self):
        company_id = (self.settings.active_company_id or "").strip()
        if not company_id:
            QMessageBox.warning(self, "No company selected", "Set active_company_id in settings.json (skeleton).")
            return
        self._run_sync(company_id)

    def _run_sync(self, company_id: str):
        self.lbl_status.setText("Syncing...")
        self.repaint()

        lic = self.sync.license_check(company_id)
        if not bool(lic.get("ok", True)):
            self.lbl_status.setText("Locked (license)")
            QMessageBox.critical(self, "License", "Subscription/trial not active. Desktop is locked.")
            return

        result = self.sync.run_once(company_id, self.device_id)
        self.lbl_status.setText(f"Synced. Pulled {result.pulled}, pushed {result.pushed}.")
