from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QMessageBox,
)

from app.auth.token_store import TokenBundle, save_tokens
from app.sync.http import ApiClient, ApiError


class LoginDialog(QDialog):
    def __init__(self, api_base_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EZ360PM Desktop — Sign in")
        self.setModal(True)

        self.api_base_url = api_base_url.rstrip("/")

        self.email = QLineEdit()
        self.email.setPlaceholderText("email@example.com")

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)

        self.btn_login = QPushButton("Sign in")
        self.btn_cancel = QPushButton("Cancel")

        self.btn_login.clicked.connect(self._on_login)
        self.btn_cancel.clicked.connect(self.reject)

        form = QFormLayout()
        form.addRow("Email", self.email)
        form.addRow("Password", self.password)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_login)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def _on_login(self):
        email = self.email.text().strip()
        password = self.password.text()
        if not email or not password:
            QMessageBox.warning(self, "Missing info", "Enter your email and password.")
            return

        api = ApiClient(self.api_base_url, TokenBundle())
        try:
            data = api.post("/api/v1/auth/token/", {"email": email, "password": password})
            access = str(data.get("access") or "")
            refresh = str(data.get("refresh") or "")
            if not access or not refresh:
                raise ApiError("Login succeeded but missing tokens.")

            tokens = TokenBundle(
                access=access,
                refresh=refresh,
                user_id=str(data.get("user_id") or ""),
                username=str(data.get("username") or ""),
            )
            save_tokens(tokens)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Login failed", str(e))
