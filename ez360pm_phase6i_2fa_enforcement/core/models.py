# core/models.py
from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class SyncQuerySet(models.QuerySet):
    """QuerySet with sync-safe soft-delete semantics."""

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        """Soft-delete in bulk (guardrail)."""
        now = timezone.now()
        # Avoid triggering model delete() for each row (fast + sync-friendly).
        return self.update(deleted_at=now, updated_at=now, revision=models.F("revision") + 1)


class SyncManager(models.Manager):
    """Default manager: hides soft-deleted rows."""

    def get_queryset(self):
        return SyncQuerySet(self.model, using=self._db).alive()


class SyncModel(models.Model):
    """
    Base model for offline-first sync.

    - UUID primary key: generated client-side to support offline creation.
    - revision: monotonically increasing integer; server increments on each write.
    - updated_at: authoritative 'last modified' timestamp (server-set).
    - deleted_at: soft delete tombstone for sync.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)

    revision = models.BigIntegerField(default=0)

    deleted_at = models.DateTimeField(null=True, blank=True)

    # Managers
    objects = SyncManager()
    all_objects = models.Manager()

    # optional provenance
    updated_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_%(class)s_set",
    )
    updated_by_device = models.UUIDField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self, *, save: bool = True):
        """Mark as deleted (tombstone) for sync-safe deletion."""
        now = timezone.now()
        self.deleted_at = now
        self.updated_at = now
        # Treat deletion as a write for sync.
        try:
            self.revision = int(self.revision or 0) + 1
        except Exception:
            self.revision = 1

        if save:
            self.save(update_fields=["deleted_at", "updated_at", "revision"])

    def delete(self, using=None, keep_parents=False, *, hard: bool = False):
        """
        Guardrail: default to soft-delete.

        Pass hard=True ONLY for true data removal (rare; typically admin/maintenance only).
        """
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.soft_delete(save=True)
        return (1, {self.__class__.__name__: 1})
