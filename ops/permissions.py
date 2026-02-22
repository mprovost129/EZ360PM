from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.contrib import messages
from django.db.models import Q

from .models import OpsRole, OpsRoleAssignment


ROLE_ORDER = {
    OpsRole.VIEWER: 10,
    OpsRole.SUPPORT: 20,
    OpsRole.FINANCE: 30,
    OpsRole.SUPEROPS: 40,
}


def _role_rank(role: str) -> int:
    try:
        return ROLE_ORDER.get(role, 0)
    except Exception:
        return 0


def user_ops_roles(user) -> set[str]:
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    if getattr(user, "is_superuser", False):
        # Superusers implicitly have all roles.
        return {r for r, _ in OpsRole.choices}
    try:
        roles = set(
            OpsRoleAssignment.objects.filter(user=user).values_list("role", flat=True)
        )
        return roles
    except Exception:
        return set()


def user_has_ops_role(user, role: str) -> bool:
    roles = user_ops_roles(user)
    if role in roles:
        return True
    # Support: allow higher roles to satisfy lower requirements.
    wanted = _role_rank(role)
    return any(_role_rank(r) >= wanted for r in roles)


def require_ops_role(request, role: str, *, message: str | None = None) -> bool:
    user = getattr(request, "user", None)
    if user_has_ops_role(user, role):
        return True
    if message:
        messages.error(request, message)
    else:
        messages.error(request, "You do not have permission to perform that action in Ops Center.")
    return False
