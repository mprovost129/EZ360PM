# catalog/models.py
from __future__ import annotations

from django.db import models

from core.models import SyncModel
from companies.models import Company


class CatalogItemType(models.TextChoices):
    SERVICE = "service", "Service"
    PRODUCT = "product", "Product"


class TaxBehavior(models.TextChoices):
    NON_TAXABLE = "non_taxable", "Non-taxable"
    TAXABLE = "taxable", "Taxable"


class CatalogItem(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="catalog_items")

    item_type = models.CharField(max_length=20, choices=CatalogItemType.choices, default=CatalogItemType.SERVICE)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")

    unit_price_cents = models.BigIntegerField(default=0)
    tax_behavior = models.CharField(max_length=20, choices=TaxBehavior.choices, default=TaxBehavior.NON_TAXABLE)

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_company_catalog_item_name"),
        ]
        indexes = [
            models.Index(fields=["company", "item_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name
