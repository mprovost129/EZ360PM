from django.contrib import admin

from core.money import format_money_cents

from .models import Vendor, Bill, BillLineItem, BillPayment, BillAttachment, RecurringBillPlan


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


class BillAttachmentInline(admin.TabularInline):
    model = BillAttachment
    extra = 0


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    def total_display(self, obj):
        return format_money_cents(obj.total_cents)
    total_display.short_description = "Total"

    def balance_display(self, obj):
        return format_money_cents(obj.balance_cents)
    balance_display.short_description = "Balance"

    list_display = ("vendor", "company", "bill_number", "issue_date", "due_date", "status", "total_display", "balance_display")
    list_filter = ("company", "status")
    search_fields = ("bill_number", "vendor__name")
    inlines = [BillLineItemInline, BillPaymentInline, BillAttachmentInline]


@admin.register(BillAttachment)
class BillAttachmentAdmin(admin.ModelAdmin):
    list_display = ("bill", "original_filename", "content_type", "file_s3_key", "uploaded_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("original_filename", "file_s3_key", "bill__bill_number", "bill__vendor__name")


@admin.register(BillPayment)
class BillPaymentAdmin(admin.ModelAdmin):
    def amount_display(self, obj):
        return format_money_cents(obj.amount_cents)
    amount_display.short_description = "Amount"

    list_display = ("bill", "payment_date", "amount_display", "payment_account", "created_at")
    list_filter = ("payment_date",)


@admin.register(BillLineItem)
class BillLineItemAdmin(admin.ModelAdmin):
    def unit_price_display(self, obj):
        return format_money_cents(obj.unit_price_cents)
    unit_price_display.short_description = "Unit price"

    def line_total_display(self, obj):
        return format_money_cents(obj.line_total_cents)
    line_total_display.short_description = "Line total"

    list_display = ("bill", "description", "quantity", "unit_price_display", "line_total_display")


@admin.register(RecurringBillPlan)
class RecurringBillPlanAdmin(admin.ModelAdmin):
    def amount_display(self, obj):
        return format_money_cents(obj.amount_cents)
    amount_display.short_description = "Amount"

    list_display = ("id", "company", "vendor", "frequency", "next_run", "amount_display", "is_active", "auto_post", "last_run_at", "created_at")
    list_filter = ("frequency", "is_active", "auto_post")
    search_fields = ("vendor__name",)
    autocomplete_fields = ("company", "vendor", "expense_account", "created_by")
    readonly_fields = ("created_at", "updated_at", "last_run_at")
