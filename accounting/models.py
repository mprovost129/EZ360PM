from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional

from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import SyncModel
from companies.models import Company
from crm.models import Client
from projects.models import Project


class AccountType(models.TextChoices):
    ASSET = "ASSET", "Asset"
    LIABILITY = "LIABILITY", "Liability"
    EQUITY = "EQUITY", "Equity"
    INCOME = "INCOME", "Income"
    EXPENSE = "EXPENSE", "Expense"


class NormalBalance(models.TextChoices):
    DEBIT = "DEBIT", "Debit"
    CREDIT = "CREDIT", "Credit"


class Account(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="accounts")
    code = models.CharField(max_length=24, blank=True, default="")
    name = models.CharField(max_length=160)
    type = models.CharField(max_length=16, choices=AccountType.choices)
    normal_balance = models.CharField(max_length=8, choices=NormalBalance.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("company", "code"), ("company", "name")]
        ordering = ["type", "code", "name"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}".strip()


class JournalEntry(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="journal_entries")
    entry_date = models.DateField(default=timezone.localdate)
    memo = models.CharField(max_length=240, blank=True, default="")

    # provenance for idempotency
    source_type = models.CharField(max_length=40, blank=True, default="")
    source_id = models.UUIDField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="journal_entries_created"
    )

    posted_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        unique_together = [("company", "source_type", "source_id")]
        ordering = ["-entry_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.entry_date} {self.memo}".strip()

    @property
    def total_debits_cents(self) -> int:
        return int(self.lines.aggregate(s=Sum("debit_cents"))["s"] or 0)

    @property
    def total_credits_cents(self) -> int:
        return int(self.lines.aggregate(s=Sum("credit_cents"))["s"] or 0)

    @property
    def is_balanced(self) -> bool:
        return self.total_debits_cents == self.total_credits_cents


    def save(self, *args, **kwargs):
        if self.pk:
            # Immutable once created (posted)
            raise ValidationError("Journal entries are immutable once posted.")
        return super().save(*args, **kwargs)


class JournalLine(SyncModel):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="journal_lines")
    description = models.CharField(max_length=240, blank=True, default="")

    debit_cents = models.IntegerField(default=0)
    credit_cents = models.IntegerField(default=0)

    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="journal_lines")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="journal_lines")

    class Meta:
        ordering = ["id"]

    def clean(self):
        # exactly one side should be >0
        d = int(self.debit_cents or 0)
        c = int(self.credit_cents or 0)
        if d < 0 or c < 0:
            raise ValueError("Debit/Credit cannot be negative.")
        if d and c:
            raise ValueError("A line cannot have both debit and credit.")
        if (not d) and (not c):
            raise ValueError("A line must have a debit or credit amount.")


    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Journal lines are immutable once posted.")
        if self.entry_id:
            # If entry already has lines, treat as posted
            if self.entry and self.entry.lines.exists():
                # allow the initial creation only; existing lines block
                pass
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        amt = self.debit_cents if self.debit_cents else -self.credit_cents
        return f"{self.account} {amt}"


@dataclass(frozen=True)
class DefaultAccountCodes:
    CASH: str = "1000"
    AR: str = "1100"
    AP: str = "2000"
    SALES_TAX_PAYABLE: str = "2100"
    CUSTOMER_CREDITS: str = "2200"
    EQUITY: str = "3000"
    REVENUE: str = "4000"
    EXPENSES: str = "6000"


DEFAULT_ACCOUNTS = [
    # Assets
    ("1000", "Cash", AccountType.ASSET, NormalBalance.DEBIT),
    ("1100", "Accounts Receivable", AccountType.ASSET, NormalBalance.DEBIT),
    # Liabilities
    ("2000", "Accounts Payable", AccountType.LIABILITY, NormalBalance.CREDIT),
    ("2100", "Sales Tax Payable", AccountType.LIABILITY, NormalBalance.CREDIT),
    ("2200", "Customer Credits", AccountType.LIABILITY, NormalBalance.CREDIT),
    # Equity
    ("3000", "Owner's Equity", AccountType.EQUITY, NormalBalance.CREDIT),
    # Income
    ("4000", "Revenue", AccountType.INCOME, NormalBalance.CREDIT),
    # Expenses
    ("6000", "Expenses", AccountType.EXPENSE, NormalBalance.DEBIT),
]


def ensure_default_chart(company: Company) -> None:
    """Idempotently ensure a minimal chart of accounts for a company."""
    for code, name, t, nb in DEFAULT_ACCOUNTS:
        Account.objects.get_or_create(
            company=company,
            code=code,
            defaults={
                "name": name,
                "type": t,
                "normal_balance": nb,
                "is_active": True,
            },
        )


def get_account(company: Company, code: str) -> Account:
    acc = Account.objects.filter(company=company, code=code).first()
    if not acc:
        ensure_default_chart(company)
        acc = Account.objects.get(company=company, code=code)
    return acc
