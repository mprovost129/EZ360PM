# expenses/models.py
from __future__ import annotations

from django.db import models

from core.models import SyncModel
from companies.models import Company, EmployeeProfile
from crm.models import Client, Vendor
from projects.models import Project


class Merchant(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="merchants")
    name = models.CharField(max_length=160)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_company_merchant_name")
        ]


class ExpenseStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    REIMBURSED = "reimbursed", "Reimbursed"
    VOID = "void", "Void"


class Expense(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="expenses")
    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL)

    merchant = models.ForeignKey(Merchant, null=True, blank=True, on_delete=models.SET_NULL)
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL)

    date = models.DateField(null=True, blank=True)
    category = models.CharField(max_length=120, blank=True, default="")

    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL)
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL)

    description = models.TextField(blank=True, default="")
    receipt = models.FileField(upload_to="expense_receipts/", blank=True, null=True)

    amount_cents = models.BigIntegerField(default=0)
    tax_cents = models.BigIntegerField(default=0)
    total_cents = models.BigIntegerField(default=0)

    status = models.CharField(max_length=20, choices=ExpenseStatus.choices, default=ExpenseStatus.DRAFT)
