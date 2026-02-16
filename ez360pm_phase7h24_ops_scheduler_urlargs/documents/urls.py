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
]
