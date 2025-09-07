# company/services.py
from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model

from company.models import CompanyMember
from core.models import Notification
from core.services import notify

User = get_user_model()


# ---------- Internal helpers ----------
def _company_users(company, exclude: Optional[User] = None) -> list[User]:  # type: ignore[type-arg]
    """
    Return all user accounts associated with a company (members + owner).

    Args:
        company: The company instance.
        exclude: An optional user to exclude (e.g. the actor).

    Returns:
        A list of User objects.
    """
    ids = set(
        CompanyMember.objects.filter(company=company).values_list("user_id", flat=True)
    )
    if getattr(company, "owner_id", None):
        ids.add(company.owner_id)
    if exclude and getattr(exclude, "id", None) in ids:
        ids.remove(exclude.id)
    return list(User.objects.filter(id__in=ids))


# ---------- Public API ----------
def notify_company(
    company,
    actor: Optional[User], # type: ignore
    text: str,
    *,
    url: str = "",
    kind: str = Notification.GENERIC,
    exclude_actor: bool = True,
) -> int:
    """
    Broadcast a notification to all users in the company.

    Args:
        company: Company instance to notify within.
        actor: The user who triggered the notification (optional).
        text: The message text.
        url: Optional link for the notification.
        kind: Notification kind (default: GENERIC).
        exclude_actor: If True, the actor will not be notified.

    Returns:
        The number of notifications created.
    """
    recipients = _company_users(company, exclude=actor if exclude_actor else None)
    count = 0
    for user in recipients:
        notify(company, user, text, actor=actor, kind=kind, url=url)
        count += 1
    return count
