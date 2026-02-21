from __future__ import annotations

from django.contrib import admin

from core.money import format_money_cents

from .models import CatalogItem


@admin.register(CatalogItem)
class CatalogItemAdmin(admin.ModelAdmin):
    list_display = ("name", "item_type", "unit_price", "tax_behavior", "is_active", "company", "created_at", "updated_at")
    list_filter = ("item_type", "tax_behavior", "is_active", "company")
    search_fields = ("name", "description")
    ordering = ("name",)

    @admin.display(description="Unit price")
    def unit_price(self, obj: CatalogItem) -> str:
        return format_money_cents(obj.unit_price_cents)
