from django.contrib import admin

from .models import CatalogItem


@admin.register(CatalogItem)
class CatalogItemAdmin(admin.ModelAdmin):
    list_display = ("name", "item_type", "unit_price", "company", "created_at", "updated_at")
    list_filter = ("item_type", "company")
    search_fields = ("name", "description")
    ordering = ("name",)

    @admin.display(description="Unit price")
    def unit_price(self, obj: CatalogItem):
        cents = int(getattr(obj, "unit_price_cents", 0) or 0)
        return f"${cents/100:,.2f}"
