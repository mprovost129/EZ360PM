from __future__ import annotations

from typing import Dict, Type

from django.db import models

from companies.models import Company, EmployeeProfile
from crm.models import Client, ClientPhone
from payables.models import Vendor
from catalog.models import CatalogItem
from documents.models import Document, DocumentLineItem, DocumentTemplate, NumberingScheme
from projects.models import Project, ProjectService
from timetracking.models import TimeEntry, TimeEntryService, TimerState
from expenses.models import Merchant, Expense
from payments.models import Payment, ClientCreditLedgerEntry, Refund, Retainer
from audit.models import AuditEvent


def sync_model_registry() -> Dict[str, Type[models.Model]]:
    """Map 'app_label.ModelName' -> model class for sync."""

    items: list[type[models.Model]] = [
        Company,
        EmployeeProfile,
        Client,
        ClientPhone,
        Vendor,
        CatalogItem,
        Project,
        ProjectService,
        DocumentTemplate,
        NumberingScheme,
        Document,
        DocumentLineItem,
        TimeEntry,
        TimeEntryService,
        TimerState,
        Merchant,
        Expense,
        Payment,
        ClientCreditLedgerEntry,
        Refund,
        Retainer,
        AuditEvent,
    ]

    registry = {f"{m._meta.app_label}.{m.__name__}": m for m in items}

    # Back-compat: older clients may still request 'crm.Vendor'
    registry.setdefault("crm.Vendor", Vendor)
    return registry
