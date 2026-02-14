from __future__ import annotations

from .models import EmployeeProfile, EmployeeRole


ROLE_ORDER = {
    EmployeeRole.STAFF: 10,
    EmployeeRole.MANAGER: 20,
    EmployeeRole.ADMIN: 30,
    EmployeeRole.OWNER: 40,
}


def has_min_role(employee: EmployeeProfile | None, minimum_role: str) -> bool:
    """True if employee.role is at least minimum_role in the hierarchy."""
    if not employee:
        return False
    return ROLE_ORDER.get(employee.role, 0) >= ROLE_ORDER.get(minimum_role, 0)


def is_manager(employee: EmployeeProfile | None) -> bool:
    return has_min_role(employee, EmployeeRole.MANAGER)


def is_admin(employee: EmployeeProfile | None) -> bool:
    return has_min_role(employee, EmployeeRole.ADMIN)


def is_owner(employee: EmployeeProfile | None) -> bool:
    return has_min_role(employee, EmployeeRole.OWNER)
