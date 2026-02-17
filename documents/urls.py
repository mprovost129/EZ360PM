from django.urls import path

from . import views
from . import views_recurring

app_name = "documents"

urlpatterns = [
    # Invoices
    path("invoices/", views.document_list, {"doc_type": "invoice"}, name="invoice_list"),
    path("invoices/new/", views.document_wizard, {"doc_type": "invoice"}, name="invoice_wizard"),
    path("invoices/<uuid:pk>/", views.document_edit, {"doc_type": "invoice"}, name="invoice_edit"),
    path("invoices/<uuid:pk>/apply-credit/", views.invoice_apply_credit, name="invoice_apply_credit"),
    path("invoices/<uuid:pk>/delete/", views.document_delete, {"doc_type": "invoice"}, name="invoice_delete"),

    # Estimates
    path("estimates/", views.document_list, {"doc_type": "estimate"}, name="estimate_list"),
    path("estimates/new/", views.document_wizard, {"doc_type": "estimate"}, name="estimate_wizard"),
    path("estimates/<uuid:pk>/", views.document_edit, {"doc_type": "estimate"}, name="estimate_edit"),
    path("estimates/<uuid:pk>/delete/", views.document_delete, {"doc_type": "estimate"}, name="estimate_delete"),

    # Proposals
    path("proposals/", views.document_list, {"doc_type": "proposal"}, name="proposal_list"),
    path("proposals/new/", views.document_wizard, {"doc_type": "proposal"}, name="proposal_wizard"),
    path("proposals/<uuid:pk>/", views.document_edit, {"doc_type": "proposal"}, name="proposal_edit"),
    path("proposals/<uuid:pk>/delete/", views.document_delete, {"doc_type": "proposal"}, name="proposal_delete"),

    
    # Credit Notes (Invoices)
    path("invoices/<uuid:invoice_pk>/credit-notes/new/", views.credit_note_create, name="credit_note_create"),
    path("invoices/credit-notes/<uuid:pk>/edit/", views.credit_note_edit, name="credit_note_edit"),
    path("invoices/credit-notes/<uuid:pk>/post/", views.credit_note_post, name="credit_note_post"),

    # Company document settings
    path("settings/documents/", views.document_settings, name="document_settings"),

    # Back-compat alias: older templates used documents:numbering
    path("settings/numbering/", views.document_settings, name="numbering"),

    # Recurring invoices
    path("invoices/recurring/", views_recurring.recurring_plan_list, name="recurring_plan_list"),
    path("invoices/recurring/new/", views_recurring.recurring_plan_create, name="recurring_plan_create"),
    path("invoices/recurring/<uuid:pk>/", views_recurring.recurring_plan_edit, name="recurring_plan_edit"),
    path("invoices/recurring/<uuid:pk>/run/", views_recurring.recurring_plan_run_now, name="recurring_plan_run_now"),
    path("invoices/recurring/<uuid:pk>/toggle/", views_recurring.recurring_plan_toggle, name="recurring_plan_toggle"),
    path("statements/collections/follow-ups/", views.collections_followups_due, name="collections_followups_due"),
    path("statements/client/<uuid:client_pk>/", views.client_statement, name="client_statement"),
    path("statements/client/<uuid:client_pk>/csv/", views.client_statement_csv, name="client_statement_csv"),
    path("statements/client/<uuid:client_pk>/pdf/", views.client_statement_pdf, name="client_statement_pdf"),
    path("statements/client/<uuid:client_pk>/email/", views.client_statement_email, name="client_statement_email"),
    path("statements/client/<uuid:client_pk>/email/preview/", views.client_statement_email_preview, name="client_statement_email_preview"),
    path("statements/client/<uuid:client_pk>/reminders/new/", views.client_statement_reminder_create, name="client_statement_reminder_create"),
    path("statements/client/<uuid:client_pk>/reminders/<uuid:reminder_pk>/cancel/", views.client_statement_reminder_cancel, name="client_statement_reminder_cancel"),
    path("statements/client/<uuid:client_pk>/reminders/<uuid:reminder_pk>/reschedule/", views.client_statement_reminder_reschedule, name="client_statement_reminder_reschedule"),
    path("statements/client/<uuid:client_pk>/reminders/<uuid:reminder_pk>/retry-now/", views.client_statement_reminder_retry_now, name="client_statement_reminder_retry_now"),
    path("statements/client/<uuid:client_pk>/collections-notes/add/", views.client_statement_collections_note_add, name="client_statement_collections_note_add"),
    path("statements/client/<uuid:client_pk>/collections-notes/<uuid:note_pk>/done/", views.client_statement_collections_note_done, name="client_statement_collections_note_done"),
    path("statements/reminders/", views.statement_reminders_list, name="statement_reminders"),
]
