from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Static sanity checks over templates (money filter loads, invalid parentheses in {% if %}, etc.)."

    def add_arguments(self, parser):
        parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure.")
        parser.add_argument("--quiet", action="store_true", help="Reduce output.")

    def handle(self, *args, **options):
        fail_fast = bool(options.get("fail_fast"))
        quiet = bool(options.get("quiet"))

        base_dir = Path(__file__).resolve().parents[4]  # project root
        templates_dir = base_dir / "templates"

        if not templates_dir.exists():
            self.stdout.write(self.style.WARNING("No templates/ directory found."))
            return

        failures = 0
        warnings = 0

        money_filter_re = re.compile(r"\|\s*(money|money_cents)\b")

        static_tag_re = re.compile(r"{%\s*static\s+[^%]+%}")
        load_static_re = re.compile(r"{%\s*load\s+[^%]*\bstatic\b[^%]*%}")

        load_money_re = re.compile(r"{%\s*load\s+[^%]*\bmoney\b[^%]*%}")

        # Rough heuristic: parentheses inside an if tag often breaks Django templates.
        # Example bad: {% if a and (b or c) %}
        if_paren_re = re.compile(r"{%\s*if\b[^%]*\([^%]*%}")

        # Warn if templates contain POST forms without {% csrf_token %}.
        # Best-effort only (includes/partials can evade detection).
        post_form_re = re.compile(
            r"<form\b[^>]*\bmethod\s*=\s*['\"]post['\"][^>]*>(.*?)</form>",
            re.IGNORECASE | re.DOTALL,
        )

        # URL tag heuristics (lightweight). We prefer namespaced view names in this codebase.
        url_tag_re = re.compile(r"{%\s*url\s+['\"]([^'\"]+)['\"]")

        for path in templates_dir.rglob("*.html"):
            rel = str(path.relative_to(base_dir))
            s = path.read_text(encoding="utf-8", errors="ignore")

            if money_filter_re.search(s) and not load_money_re.search(s):
                failures += 1
                if not quiet:
                    self.stdout.write(self.style.ERROR(f"{rel}: uses |money or |money_cents but does not load the 'money' tag library"))
                if fail_fast:
                    raise SystemExit(2)

            if static_tag_re.search(s) and not load_static_re.search(s):
                warnings += 1
                if not quiet:
                    self.stdout.write(self.style.WARNING(f"{rel}: uses the static tag but does not load the 'static' tag library"))

            if if_paren_re.search(s):
                # Not always invalid, but in Django templates it's usually a bug.
                warnings += 1
                if not quiet:
                    self.stdout.write(self.style.WARNING(f"{rel}: possible invalid parentheses inside {{% if %}} tag"))

            # POST forms should have csrf_token
            for m in post_form_re.finditer(s):
                inner = m.group(1) or ""
                if "{% csrf_token %}" not in inner:
                    warnings += 1
                    if not quiet:
                        self.stdout.write(self.style.WARNING(f"{rel}: POST form missing {{% csrf_token %}}"))
                    break

            # URL tag heuristics (warn only)
            for m in url_tag_re.finditer(s):
                viewname = (m.group(1) or "").strip()
                if viewname and ":" not in viewname:
                    warnings += 1
                    if not quiet:
                        self.stdout.write(self.style.WARNING(f"{rel}: url tag uses un-namespaced viewname '{viewname}'"))
                    break

        if failures:
            raise SystemExit(2)

        if not quiet:
            self.stdout.write(self.style.SUCCESS(f"Template sanity check OK ({warnings} warnings)."))