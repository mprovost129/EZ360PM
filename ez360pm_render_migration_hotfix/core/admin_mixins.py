from __future__ import annotations

from django.contrib import admin


class IncludeSoftDeletedAdminMixin:
    """Admin mixin to include soft-deleted rows in changelist."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        model = getattr(self, "model", None)
        all_mgr = getattr(model, "all_objects", None)
        if all_mgr is not None:
            return all_mgr.all()
        return qs

