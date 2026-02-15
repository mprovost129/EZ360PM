from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog

from app.auth.token_store import load_tokens
from app.settings.local_settings import load_settings
from app.ui.lodin_dialog import LoginDialog
from app.ui.shell import AppShell


def load_schema_sql() -> str:
    # schema.sql is located at ez360pm_desktop/schema.sql
    here = Path(__file__).resolve()
    schema_path = here.parents[1] / "schema.sql"
    return schema_path.read_text(encoding="utf-8")


def main() -> int:
    app = QApplication(sys.argv)

    settings = load_settings()
    tokens = load_tokens()

    if not tokens.access or not tokens.refresh:
        dlg = LoginDialog(settings.base_url)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return 0

    shell = AppShell(load_schema_sql())
    shell.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
