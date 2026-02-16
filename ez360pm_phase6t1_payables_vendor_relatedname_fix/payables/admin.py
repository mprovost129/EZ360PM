from django.contrib import admin

from .models import Vendor, Bill, BillLineItem, BillPayment


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "email", "phone", "is_active", "updated_at")
    list_filter = ("company", "is_active")
    search_fields = ("name", "email", "phone")


class BillLineItemInline(admin.TabularInline):
    model = BillLineItem
    extra = 0


class BillPaymentInline(admin.TabularInline):
    model = BillPayment
    extra = 0


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ("vendor", "company", "bill_number", "issue_date", "due_date", "status", "total_cents", "balance_cents")
    list_filter = ("company", "status")
    search_fields = ("bill_number", "vendor__name")
    inlines = [BillLineItemInline, BillPaymentInline]


@admin.register(BillPayment)
class BillPaymentAdmin(admin.ModelAdmin):
    list_display = ("bill", "payment_date", "amount_cents", "payment_account", "created_at")
    list_filter = ("payment_date",)


@admin.register(BillLineItem)
class BillLineItemAdmin(admin.ModelAdmin):
    list_display = ("bill", "description", "quantity", "unit_price_cents", "line_total_cents")
