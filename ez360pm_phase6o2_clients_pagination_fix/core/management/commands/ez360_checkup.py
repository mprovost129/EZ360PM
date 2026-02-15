from __future__ import annotations

import os
from django.core.management.base import BaseCommand


REQUIRED_ALWAYS = [
    "SECRET_KEY",
]

RECOMMENDED_PROD = [
    "ALLOWED_HOSTS",
    "CSRF_TRUSTED_ORIGINS",
    "DATABASE_URL",
]

EMAIL_KEYS = [
    "EMAIL_HOST",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
]

STRIPE_KEYS = [
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
]


class Command(BaseCommand):
    help = "Check environment configuration for EZ360PM."

    def handle(self, *args, **options):
        missing_always = [k for k in REQUIRED_ALWAYS if not os.environ.get(k)]
        missing_recommended = [k for k in RECOMMENDED_PROD if not os.environ.get(k)]

        self.stdout.write("EZ360PM configuration check")
        self.stdout.write("-" * 32)

        if missing_always:
            self.stdout.write(self.style.ERROR("Missing required env vars:"))
            for k in missing_always:
                self.stdout.write(f"  - {k}")
        else:
            self.stdout.write(self.style.SUCCESS("Required env vars: OK"))

        if missing_recommended:
            self.stdout.write(self.style.WARNING("Recommended for production (missing):"))
            for k in missing_recommended:
                self.stdout.write(f"  - {k}")
        else:
            self.stdout.write(self.style.SUCCESS("Recommended production env vars: OK"))

        # Email optional
        email_present = [k for k in EMAIL_KEYS if os.environ.get(k)]
        if email_present:
            missing_email = [k for k in EMAIL_KEYS if not os.environ.get(k)]
            if missing_email:
                self.stdout.write(self.style.WARNING("Email appears partially configured; missing:"))
                for k in missing_email:
                    self.stdout.write(f"  - {k}")
            else:
                self.stdout.write(self.style.SUCCESS("Email env vars: OK"))

        # Stripe optional
        stripe_present = [k for k in STRIPE_KEYS if os.environ.get(k)]
        if stripe_present:
            missing_stripe = [k for k in STRIPE_KEYS if not os.environ.get(k)]
            if missing_stripe:
                self.stdout.write(self.style.WARNING("Stripe appears partially configured; missing:"))
                for k in missing_stripe:
                    self.stdout.write(f"  - {k}")
            else:
                self.stdout.write(self.style.SUCCESS("Stripe env vars: OK"))

        if missing_always:
            raise SystemExit(2)
