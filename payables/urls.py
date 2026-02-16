from django.urls import path

from . import views

app_name = "payables"

urlpatterns = [
    path("payables/vendors/", views.vendor_list, name="vendor_list"),
    path("payables/vendors/new/", views.vendor_create, name="vendor_create"),
    path("payables/vendors/<uuid:pk>/edit/", views.vendor_edit, name="vendor_edit"),
    path("payables/vendors/<uuid:pk>/", views.vendor_detail, name="vendor_detail"),

    path("payables/bills/", views.bill_list, name="bill_list"),
    path("payables/bills/new/", views.bill_create, name="bill_create"),
    path("payables/bills/<uuid:pk>/", views.bill_detail, name="bill_detail"),
    path("payables/bills/<uuid:pk>/edit/", views.bill_edit, name="bill_edit"),
    path("payables/bills/<uuid:pk>/post/", views.bill_post, name="bill_post"),
    path("payables/bills/<uuid:pk>/lines/add/", views.bill_add_line, name="bill_add_line"),
    path("payables/bills/<uuid:pk>/lines/<uuid:line_id>/delete/", views.bill_delete_line, name="bill_delete_line"),
    path("payables/bills/<uuid:pk>/payments/add/", views.bill_add_payment, name="bill_add_payment"),

    path("payables/bills/<uuid:pk>/attachments/add/", views.bill_add_attachment, name="bill_add_attachment"),
    path("payables/bills/<uuid:pk>/attachments/<uuid:attachment_id>/delete/", views.bill_delete_attachment, name="bill_delete_attachment"),
    path("payables/bills/<uuid:pk>/attachments/<uuid:attachment_id>/download/", views.bill_attachment_download, name="bill_attachment_download"),


    path("payables/recurring-bills/", views.recurring_bill_plan_list, name="recurring_bill_plan_list"),
    path("payables/recurring-bills/new/", views.recurring_bill_plan_create, name="recurring_bill_plan_create"),
    path("payables/recurring-bills/<uuid:pk>/edit/", views.recurring_bill_plan_edit, name="recurring_bill_plan_edit"),
    path("payables/recurring-bills/<uuid:pk>/delete/", views.recurring_bill_plan_delete, name="recurring_bill_plan_delete"),
    path("payables/recurring-bills/<uuid:pk>/run-now/", views.recurring_bill_plan_run_now, name="recurring_bill_plan_run_now"),

    path("payables/reports/ap-aging/", views.ap_aging_report, name="ap_aging_report"),
    path("payables/reports/ap-aging.csv", views.ap_aging_report_csv, name="ap_aging_report_csv"),
]
