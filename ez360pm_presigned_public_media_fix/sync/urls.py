from __future__ import annotations

from django.urls import path

from .views import DeviceRegisterAPI, LicenseCheckAPI, SyncPullAPI, SyncPushAPI


app_name = "sync"


urlpatterns = [
    path("devices/register/", DeviceRegisterAPI.as_view(), name="device_register"),
    path("license/check/", LicenseCheckAPI.as_view(), name="license_check"),
    path("pull/", SyncPullAPI.as_view(), name="pull"),
    path("push/", SyncPushAPI.as_view(), name="push"),
]
