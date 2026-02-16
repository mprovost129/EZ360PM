from __future__ import annotations

from typing import Any, Dict, List

from django.db import transaction
from django.utils import timezone
from django.db.models import Q

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.services import build_subscription_summary
from companies.models import Company
from .models import SyncDevice, SyncCursor, DevicePlatform
from .registry import sync_model_registry
from .utils import model_to_sync_dict, parse_iso_datetime, apply_lww_change


class DeviceRegisterAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Register a sync device.

        Request JSON:
          {"company_id": "...", "platform": "windows", "name": "My PC", "device_id": "optional uuid"}
        """
        payload = request.data or {}
        company_id = payload.get("company_id")
        platform = (payload.get("platform") or "windows").lower()
        name = (payload.get("name") or "").strip()
        device_id = payload.get("device_id")

        company = Company.objects.get(id=company_id)

        # Ensure the user belongs to this company
        if not company.employees.filter(user=request.user, deleted_at__isnull=True).exists():
            return Response({"detail": "Not a member of this company."}, status=403)

        defaults = {
            "company": company,
            "user": request.user,
            "platform": platform if platform in {"web", "windows"} else DevicePlatform.WINDOWS,
            "name": name,
            "last_seen_at": timezone.now(),
        }

        if device_id:
            device, _ = SyncDevice.objects.update_or_create(id=device_id, defaults=defaults)
        else:
            device = SyncDevice.objects.create(**defaults)

        SyncCursor.objects.get_or_create(company=company, device=device)

        return Response({"device_id": str(device.id), "company_id": str(company.id)})


class LicenseCheckAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = request.data or {}
        company_id = payload.get("company_id")
        company = Company.objects.get(id=company_id)

        if not company.employees.filter(user=request.user, deleted_at__isnull=True).exists():
            return Response({"detail": "Not a member of this company."}, status=403)

        sub = getattr(company, "subscription", None)
        if not sub:
            # Unsubscribed
            return Response(
                {
                    "status": "none",
                    "plan": None,
                    "billing_interval": None,
                    "extra_seats": 0,
                    "seats_limit": 0,
                    "active_or_trial": False,
                    "trial_days": 14,
                }
            )

        # stamp license check
        sub.last_license_check_at = timezone.now()
        sub.save(update_fields=["last_license_check_at"])

        return Response(
            {
                "status": sub.status,
                "plan": sub.plan,
                "billing_interval": sub.billing_interval,
                "extra_seats": int(sub.extra_seats or 0),
                "seats_limit": build_subscription_summary(company).seats_limit,
                "trial_started_at": sub.trial_started_at.isoformat() if sub.trial_started_at else None,
                "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
                "active_or_trial": sub.is_active_or_trial(),
            }
        )


class SyncPullAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_id = request.query_params.get("company_id")
        since_raw = request.query_params.get("since")
        limit = int(request.query_params.get("limit") or 5000)

        company = Company.objects.get(id=company_id)
        if not company.employees.filter(user=request.user, deleted_at__isnull=True).exists():
            return Response({"detail": "Not a member of this company."}, status=403)

        since = parse_iso_datetime(since_raw) if since_raw else None
        server_now = timezone.now()

        registry = sync_model_registry()
        entities: Dict[str, List[Dict[str, Any]]] = {}

        for key, model_cls in registry.items():
            mgr = getattr(model_cls, "all_objects", model_cls.objects)
            qs = mgr.all()
            if hasattr(model_cls, "company_id"):
                qs = qs.filter(company_id=company.id)

            if since:
                qs = qs.filter(Q(updated_at__gt=since) | Q(deleted_at__gt=since))

            qs = qs.order_by("updated_at")[:limit]
            items = [model_to_sync_dict(obj) for obj in qs]
            if items:
                entities[key] = items

        return Response(
            {
                "server_time": server_now.isoformat(),
                "next_since": server_now.isoformat(),
                "entities": entities,
            }
        )


class SyncPushAPI(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        payload = request.data or {}
        company_id = payload.get("company_id")
        device_id = payload.get("device_id")
        changes = payload.get("changes") or {}

        company = Company.objects.get(id=company_id)
        if not company.employees.filter(user=request.user, deleted_at__isnull=True).exists():
            return Response({"detail": "Not a member of this company."}, status=403)

        device = SyncDevice.objects.get(id=device_id)
        if device.company_id != company.id or device.user_id != request.user.id:
            return Response({"detail": "Invalid device."}, status=403)

        server_now = timezone.now()
        registry = sync_model_registry()

        results: Dict[str, List[Dict[str, Any]]] = {}

        for model_key, change_list in changes.items():
            model_cls = registry.get(model_key)
            if not model_cls:
                continue

            model_results: List[Dict[str, Any]] = []
            for change in change_list or []:
                obj_id = change.get("id")
                client_updated_at = parse_iso_datetime(change.get("updated_at"))
                deleted_at = parse_iso_datetime(change.get("deleted_at"))
                fields = change.get("fields") or {}

                obj, _created = model_cls.objects.get_or_create(id=obj_id)

                # enforce company scoping
                if hasattr(obj, "company_id"):
                    if getattr(obj, "company_id", None) and obj.company_id != company.id:
                        model_results.append({"id": obj_id, "status": "rejected_wrong_company"})
                        continue
                    obj.company_id = company.id

                # deletes
                if deleted_at:
                    # LWW on deletes too
                    applied = False
                    if not getattr(obj, "deleted_at", None) or (client_updated_at and client_updated_at > obj.updated_at):
                        obj.deleted_at = server_now
                        obj.updated_at = server_now
                        obj.revision = int(getattr(obj, "revision", 0) or 0) + 1
                        obj.updated_by_user = request.user
                        obj.updated_by_device = device.id
                        obj.save()
                        applied = True

                    model_results.append(
                        {
                            "id": obj_id,
                            "status": "applied" if applied else "conflict_overwritten",
                            "server_revision": int(obj.revision or 0),
                            "server_updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
                        }
                    )
                    continue

                # normal update
                _obj, applied = apply_lww_change(
                    obj=obj,
                    fields=fields,
                    client_updated_at=client_updated_at,
                    server_now=server_now,
                    updated_by_user_id=request.user.id,
                    updated_by_device=str(device.id),
                )

                model_results.append(
                    {
                        "id": obj_id,
                        "status": "applied" if applied else "conflict_overwritten",
                        "server_revision": int(obj.revision or 0),
                        "server_updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
                    }
                )

            if model_results:
                results[model_key] = model_results

        # cursor update
        cursor, _ = SyncCursor.objects.get_or_create(company=company, device=device)
        cursor.last_pushed_at = server_now
        cursor.save(update_fields=["last_pushed_at"])

        device.last_seen_at = server_now
        device.save(update_fields=["last_seen_at"])

        return Response({"server_time": server_now.isoformat(), "results": results})
