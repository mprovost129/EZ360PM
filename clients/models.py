# clients/models.py
from __future__ import annotations

from django.db import models


class Client(models.Model):
    """
    A client (customer) record belonging to a tenant Company.
    Each tenant manages its own set of clients.
    """

    company = models.ForeignKey(
        "company.company",
        on_delete=models.CASCADE,
        related_name="clients",
        help_text="The tenant company that owns this client record.",
    )

    # Client's own organization (not to be confused with the tenant's company)
    org = models.CharField("Client company", max_length=200, blank=True)

    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)

    address_1 = models.CharField("Address line 1", max_length=200, blank=True)
    address_2 = models.CharField("Address line 2", max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    zip_code = models.CharField("ZIP / Postal code", max_length=20, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "client"
        verbose_name_plural = "clients"
        ordering = ("org", "last_name", "first_name", "id")
        indexes = [
            models.Index(fields=["company", "org"]),
            models.Index(fields=["company", "email"]),
            models.Index(fields=["company", "last_name", "first_name"]),
        ]
        constraints = [
            # Prevent duplicates within the same tenant, but allow same email across tenants.
            models.UniqueConstraint(
                fields=["company", "email"],
                name="uniq_client_per_company_email",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name or self.email

    def __repr__(self) -> str:
        return f"<Client id={self.pk} {self.display_name!r} email={self.email!r}>"

    # -----------------------------
    # Convenience properties
    # -----------------------------
    @property
    def full_name(self) -> str:
        return f"{(self.first_name or '').strip()} {(self.last_name or '').strip()}".strip()

    @property
    def display_name(self) -> str:
        """Prefer the client's org/company; else a human name; else email."""
        return self.org or self.full_name or ""

    @property
    def short_address(self) -> str:
        """One-line summary address (useful in dropdowns)."""
        parts = [self.city, self.state, self.zip_code]
        return ", ".join(p for p in parts if p).strip()

