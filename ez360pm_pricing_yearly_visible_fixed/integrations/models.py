from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from companies.models import Company


class DropboxConnection(models.Model):
    """One Dropbox connection per company (v1)."""

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="dropbox_connection")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_dropbox_connections"
    )

    # WARNING: stored in DB. Consider encryption-at-rest later.
    access_token = models.TextField(blank=True, default="")
    account_id = models.CharField(max_length=128, blank=True, default="")
    token_type = models.CharField(max_length=32, blank=True, default="")
    scope = models.CharField(max_length=512, blank=True, default="")

    expires_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_inactive(self) -> None:
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    def __str__(self) -> str:
        return f"DropboxConnection(company={self.company_id}, active={self.is_active})"


class IntegrationConfig(models.Model):
    """Per-company integration preferences (v1)."""

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="integration_config")
    use_dropbox_for_project_files = models.BooleanField(
        default=False,
        help_text="If enabled, new Project Files will also be uploaded to Dropbox when connected.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"IntegrationConfig(company={self.company_id})"


class BankConnection(models.Model):
    """Bank feed connection per company.

    v1 is a scaffold (Plaid-style semantics) so we can support importing
    transactions and mapping them to Expenses in future packs.
    """

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="bank_connection")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bank_connections",
    )

    provider = models.CharField(max_length=32, default="plaid")

    # WARNING: stored in DB. Consider encryption-at-rest later.
    access_token = models.TextField(blank=True, default="")
    item_id = models.CharField(max_length=128, blank=True, default="")
    sync_cursor = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=32, blank=True, default="")
    last_sync_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_inactive(self) -> None:
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    def __str__(self) -> str:
        return f"BankConnection(company={self.company_id}, active={self.is_active})"


class BankAccount(models.Model):
    connection = models.ForeignKey(BankConnection, on_delete=models.CASCADE, related_name="accounts")
    account_id = models.CharField(max_length=128)
    name = models.CharField(max_length=128, blank=True, default="")
    mask = models.CharField(max_length=8, blank=True, default="")
    type = models.CharField(max_length=32, blank=True, default="")
    subtype = models.CharField(max_length=64, blank=True, default="")
    currency = models.CharField(max_length=8, blank=True, default="USD")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("connection", "account_id")]

    def __str__(self) -> str:
        return f"BankAccount({self.name or self.account_id})"


class BankTransaction(models.Model):
    """Raw transaction record imported from the bank feed."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        IGNORED = "ignored", "Ignored"
        TRANSFER = "transfer", "Transfer"
        EXPENSE_CREATED = "expense_created", "Expense created"

    account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="transactions")
    transaction_id = models.CharField(max_length=128)
    posted_date = models.DateField(null=True, blank=True)
    name = models.CharField(max_length=255, blank=True, default="")
    amount_cents = models.IntegerField(default=0)
    is_pending = models.BooleanField(default=False)
    category = models.CharField(max_length=255, blank=True, default="")

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.NEW)
    suggested_merchant_name = models.CharField(max_length=160, blank=True, default="")
    suggested_category = models.CharField(max_length=120, blank=True, default="")

    linked_expense = models.ForeignKey(
        "expenses.Expense",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bank_transactions",
    )

    # Duplicate prevention / matching heuristics
    suggested_existing_expense = models.ForeignKey(
        "expenses.Expense",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bank_transactions_suggested",
        help_text="Potential existing expense match suggested by heuristics (non-binding).",
    )
    suggested_existing_expense_score = models.PositiveSmallIntegerField(default=0)

    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_bank_transactions",
    )
    applied_rule = models.ForeignKey(
        "integrations.BankRule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matched_transactions",
    )
    raw = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("account", "transaction_id")]
        indexes = [
            models.Index(fields=["posted_date"]),
            models.Index(fields=["is_pending"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"BankTransaction({self.transaction_id})"


class BankRule(models.Model):
    """Rules for categorizing and triaging imported transactions.

    v1: basic merchant/name matching to suggest category/merchant, ignore, or mark transfers.
    """

    class MatchField(models.TextChoices):
        NAME = "name", "Merchant / Name"
        CATEGORY = "category", "Bank category"

    class MatchType(models.TextChoices):
        CONTAINS = "contains", "Contains"
        STARTS_WITH = "starts_with", "Starts with"
        EQUALS = "equals", "Equals"

    class Action(models.TextChoices):
        SUGGEST = "suggest", "Suggest category"
        IGNORE = "ignore", "Ignore"
        TRANSFER = "transfer", "Mark as transfer"
        AUTO_CREATE_EXPENSE = "auto_create_expense", "Auto-create draft expense"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="bank_rules")
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100, help_text="Lower runs first.")

    match_field = models.CharField(max_length=24, choices=MatchField.choices, default=MatchField.NAME)
    match_type = models.CharField(max_length=24, choices=MatchType.choices, default=MatchType.CONTAINS)
    match_text = models.CharField(max_length=160)

    # Optional amount guardrails (in cents). Leave blank for any amount.
    min_amount_cents = models.IntegerField(null=True, blank=True)
    max_amount_cents = models.IntegerField(null=True, blank=True)

    # For suggestions / expense creation
    merchant_name = models.CharField(max_length=160, blank=True, default="")
    expense_category = models.CharField(max_length=120, blank=True, default="")
    action = models.CharField(max_length=32, choices=Action.choices, default=Action.SUGGEST)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "id"]

    def __str__(self) -> str:
        return f"BankRule(company={self.company_id}, action={self.action}, match={self.match_text})"


class BankReconciliationPeriod(models.Model):
    """A reconciliation window for bank transactions vs expenses.

    Phase 9: provide an auditable, lockable period so teams can reconcile and
    then "freeze" a window (until explicitly undone).
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        LOCKED = "locked", "Locked"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="bank_reconciliation_periods")
    start_date = models.DateField()
    end_date = models.DateField()

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="locked_bank_reconciliation_periods",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_bank_reconciliation_periods",
    )

    notes = models.TextField(blank=True, default="")

    # Snapshot fields (written on lock for transparency)
    snapshot_bank_outflow_cents = models.BigIntegerField(default=0)
    snapshot_expense_total_cents = models.BigIntegerField(default=0)
    snapshot_matched_count = models.PositiveIntegerField(default=0)
    snapshot_unmatched_bank_count = models.PositiveIntegerField(default=0)
    snapshot_unmatched_expense_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        indexes = [
            models.Index(fields=["company", "start_date", "end_date"]),
            models.Index(fields=["company", "status"]),
        ]

    def lock(self, *, by_user) -> None:
        if self.status == self.Status.LOCKED:
            return
        self.status = self.Status.LOCKED
        self.locked_at = timezone.now()
        self.locked_by = by_user
        self.save(update_fields=["status", "locked_at", "locked_by", "updated_at"])

    def unlock(self) -> None:
        if self.status != self.Status.LOCKED:
            return
        self.status = self.Status.OPEN
        self.locked_at = None
        self.locked_by = None
        # keep snapshot fields for history (transparency)
        self.save(update_fields=["status", "locked_at", "locked_by", "updated_at"])

    def __str__(self) -> str:
        return f"BankReconciliationPeriod(company={self.company_id}, {self.start_date}→{self.end_date}, {self.status})"
