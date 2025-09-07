# core/models.py
from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

UserModelRef = settings.AUTH_USER_MODEL  # e.g. "accounts.User"


# -----------------------------
# Notifications
# -----------------------------

class NotificationQuerySet(models.QuerySet):
    """Convenience filters and bulk ops for notifications."""

    def for_company_user(self, company, user):
        if not company or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(company=company, recipient=user)

    def unread(self):
        return self.filter(read_at__isnull=True)

    def read(self):
        return self.filter(read_at__isnull=False)

    def mark_all_read(self) -> int:
        """Mark all in the queryset as read. Returns rows updated."""
        now = timezone.now()
        return self.filter(read_at__isnull=True).update(read_at=now)


class NotificationManager(models.Manager):
    """Creates notifications with a simple, uniform API."""

    def get_queryset(self) -> NotificationQuerySet:  # type: ignore[override]
        return NotificationQuerySet(self.model, using=self._db)

    # Simple factories (extend as needed)
    def create_generic(
        self,
        *,
        company,
        recipient,
        text: str,
        url: str = "",
        actor: Optional[settings.AUTH_USER_MODEL] = None, # type: ignore
        target: Optional[models.Model] = None,
        kind: str = "generic",
    ) -> "Notification":
        ct = oid = None
        if target is not None:
            ct = ContentType.objects.get_for_model(target, for_concrete_model=False)
            oid = target.pk
        return self.create(
            company=company,
            recipient=recipient,
            actor=actor,
            kind=kind,
            text=text,
            url=url,
            target_content_type=ct,
            target_object_id=oid,
        )


class Notification(models.Model):
    """User-facing, company-scoped notifications with optional targets."""

    GENERIC = "generic"
    INVOICE_CREATED = "invoice_created"
    INVOICE_PAID = "invoice_paid"
    ESTIMATE_ACCEPTED = "estimate_accepted"
    ESTIMATE_CREATED = "estimate_created"
    ESTIMATE_CONVERTED = "estimate_converted"
    PROJECT_CREATED = "project_created"
    TIME_ADDED = "time_added"
    EXPENSE_ADDED = "expense_added"

    KIND_CHOICES = [
        (GENERIC, "Generic"),
        (INVOICE_CREATED, "Invoice created"),
        (INVOICE_PAID, "Invoice paid"),
        (ESTIMATE_ACCEPTED, "Estimate accepted"),
        (ESTIMATE_CREATED, "Estimate created"),
        (ESTIMATE_CONVERTED, "Estimate converted"),
        (PROJECT_CREATED, "Project created"),
        (TIME_ADDED, "Time added"),
        (EXPENSE_ADDED, "Expense added"),
    ]

    company = models.ForeignKey(
        "company.company",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    recipient = models.ForeignKey(
        UserModelRef,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        UserModelRef,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_sent",
    )

    kind = models.CharField(max_length=40, choices=KIND_CHOICES, default=GENERIC)
    text = models.CharField(max_length=280)
    # CharField rather than URLField so internal paths ("/invoices/123/") are allowed.
    url = models.CharField(max_length=500, blank=True, default="")

    # Optional target object
    target_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    objects: NotificationManager = NotificationManager() # type: ignore

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=["company", "recipient", "read_at", "created_at"]),
            models.Index(fields=["recipient", "read_at", "created_at"]),
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]

    @property
    def is_read(self) -> bool:
        return bool(self.read_at)

    def mark_read(self, *, save: bool = True) -> None:
        if not self.read_at:
            self.read_at = timezone.now()
            if save:
                self.save(update_fields=["read_at"])

    def link(self) -> str:
        """Best-guess URL for the notification."""
        if self.url:
            return self.url
        if self.target and hasattr(self.target, "get_absolute_url"):
            try:
                return self.target.get_absolute_url()  # type: ignore[no-any-return]
            except Exception:
                pass
        return ""

    def clean(self) -> None:
        """
        Optional sanity check: keep recipient/actor company-aligned.
        Adjust this if your multi-tenant model links companies differently.
        """
        # If your user has a `company` FK, uncomment and enforce:
        # if getattr(self.recipient, "company_id", None) and self.recipient.company_id != self.company_id:
        #     raise ValidationError({"recipient": "Recipient is not a member of this company."})
        # if self.actor and getattr(self.actor, "company_id", None) and self.actor.company_id != self.company_id:
        #     raise ValidationError({"actor": "Actor is not a member of this company."})
        return super().clean()

    def __str__(self) -> str:
        who = getattr(self.recipient, "email", str(self.recipient))
        return f"{who} · {self.text}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Notification id={self.pk} kind={self.kind} recipient={self.recipient_id}>" # type: ignore


# -----------------------------
# Suggestions / Feedback
# -----------------------------

class Suggestion(models.Model):
    """Lightweight feedback box for users and visitors."""

    STATUS_NEW = "new"
    STATUS_REVIEWED = "reviewed"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_CLOSED, "Closed"),
    ]

    company = models.ForeignKey(
        "company.company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="suggestions",
    )
    user = models.ForeignKey(
        UserModelRef,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="suggestions",
    )

    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    page_url = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Suggestion"
        verbose_name_plural = "Suggestions"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["company", "status", "created_at"]),
        ]

    def __str__(self) -> str:
        who = self.name or self.email or (getattr(self.user, "email", "") or "Anon")
        return f"{who} — {self.subject[:60]}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Suggestion id={self.pk} status={self.status}>"


