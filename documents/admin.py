from django.contrib import admin

from .models import Document, DocumentLineItem, DocumentTemplate, NumberingScheme, CreditNote, CreditNoteNumberSequence


class DocumentLineItemInline(admin.TabularInline):
    model = DocumentLineItem
    extra = 0
    fields = ("sort_order", "name", "qty", "unit_price_cents", "tax_cents", "line_total_cents", "deleted_at")
    readonly_fields = ("line_total_cents",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("doc_type", "number", "company", "client", "project", "status", "total_cents", "created_at")
    list_filter = ("doc_type", "status", "company")
    search_fields = ("number", "title", "client__first_name", "client__last_name", "client__company_name")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [DocumentLineItemInline]


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ("company", "doc_type", "name", "is_active", "created_at")
    list_filter = ("company", "doc_type", "is_active")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(NumberingScheme)
class NumberingSchemeAdmin(admin.ModelAdmin):
    list_display = ("company", "invoice_pattern", "estimate_pattern", "proposal_pattern")
    readonly_fields = ("id", "created_at", "updated_at", "invoice_seq", "estimate_seq", "proposal_seq")


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ("number", "company", "invoice", "status", "total_cents", "created_at")
    list_filter = ("status", "company")
    search_fields = ("number", "invoice__number", "reason")
    readonly_fields = ("id", "created_at", "updated_at", "posted_at", "journal_entry")
    actions = ["post_selected_credit_notes"]


    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and getattr(obj, "status", "") == "posted":
            # lock everything for posted credit notes
            ro += ["company", "invoice", "created_by", "number", "status", "subtotal_cents", "tax_cents", "total_cents", "reason"]
        return ro

    def post_selected_credit_notes(self, request, queryset):
        from accounting.services import post_credit_note_if_needed
        posted = 0
        skipped = 0
        for cn in queryset:
            try:
                entry = post_credit_note_if_needed(cn)
                if entry:
                    posted += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
        self.message_user(request, f"Posted {posted} credit note(s). Skipped {skipped}.")

    post_selected_credit_notes.short_description = "Post selected credit notes"



@admin.register(CreditNoteNumberSequence)
class CreditNoteNumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("company", "next_number")
    search_fields = ("company__name",)
