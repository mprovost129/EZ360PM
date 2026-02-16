from django.urls import path

from . import views

app_name = "payables"

urlpatterns = [
    path("payables/vendors/", views.vendor_list, name="vendor_list"),
    path("payables/vendors/new/", views.vendor_create, name="vendor_create"),
    path("payables/vendors/<uuid:pk>/edit/", views.vendor_edit, name="vendor_edit"),

    path("payables/bills/", views.bill_list, name="bill_list"),
    path("payables/bills/new/", views.bill_create, name="bill_create"),
    path("payables/bills/<uuid:pk>/", views.bill_detail, name="bill_detail"),
    path("payables/bills/<uuid:pk>/edit/", views.bill_edit, name="bill_edit"),
    path("payables/bills/<uuid:pk>/post/", views.bill_post, name="bill_post"),
    path("payables/bills/<uuid:pk>/lines/add/", views.bill_add_line, name="bill_add_line"),
    path("payables/bills/<uuid:pk>/lines/<uuid:line_id>/delete/", views.bill_delete_line, name="bill_delete_line"),
    path("payables/bills/<uuid:pk>/payments/add/", views.bill_add_payment, name="bill_add_payment"),
]
