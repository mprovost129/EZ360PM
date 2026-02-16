from django.contrib import admin

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
    list_display = ("vendor", "company", "bill_number", "issue_date", "due_date", "status", "total_cents", "balance_cents")
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
    list_display = ("bill", "payment_date", "amount_cents", "payment_account", "created_at")
    list_filter = ("payment_date",)


@admin.register(BillLineItem)
class BillLineItemAdmin(admin.ModelAdmin):
    list_display = ("bill", "description", "quantity", "unit_price_cents", "line_total_cents")


@admin.register(RecurringBillPlan)
class RecurringBillPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "vendor", "frequency", "next_run", "amount_cents", "is_active", "auto_post", "last_run_at", "created_at")
    list_filter = ("frequency", "is_active", "auto_post")
    search_fields = ("vendor__name",)
    autocomplete_fields = ("company", "vendor", "expense_account", "created_by")
    readonly_fields = ("created_at", "updated_at", "last_run_at")
