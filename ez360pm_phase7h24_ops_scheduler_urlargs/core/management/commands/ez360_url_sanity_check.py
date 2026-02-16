from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from django.core.management.base import BaseCommand
from django.urls import get_resolver


# Capture the full tag body so we can heuristically count positional args.
# Examples:
#   {% url 'foo:bar' %}
#   {% url "foo:bar" obj.pk %}
#   {% url 'foo:bar' a b as the_url %}
URL_TAG_FULL_RE = re.compile(
    r"{%\s*url\s+(?P<q>['\"])(?P<name>[^'\"]+)(?P=q)(?P<rest>[^%]*)%}",
    re.MULTILINE,
)


class Command(BaseCommand):
    help = "Static sanity check for template {% url %} usage (best-effort)."

    def add_arguments(self, parser):
        parser.add_argument("--quiet", action="store_true", help="Reduce output.")
        parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure.")
        parser.add_argument(
            "--templates-dir",
            default="templates",
            help="Templates root dir (default: templates).",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=20,
            help="Validate arg counts for the top N most-used url names (default: 20).",
        )

    def handle(self, *args, **opts):
        quiet = bool(opts["quiet"])
        fail_fast = bool(opts["fail_fast"])
        templates_dir = Path(opts["templates_dir"]).resolve()
        top_n = int(opts["top"] or 20)

        resolver = get_resolver()
        reverse_keys = set(resolver.reverse_dict.keys())

        total = 0
        missing = 0
        warnings = 0

        def out(msg: str):
            if not quiet:
                self.stdout.write(msg)

        if not templates_dir.exists():
            out(f"OK: templates dir not found at {templates_dir} (skipping).")
            return

        # Pass 1: gather all url tags and count viewname usage.
        occurrences: list[tuple[Path, str, str]] = []  # (path, name, rest)
        freq: Counter[str] = Counter()

        for path in templates_dir.rglob("*.html"):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue

            for m in URL_TAG_FULL_RE.finditer(text):
                name = (m.group("name") or "").strip()
                rest = (m.group("rest") or "")
                if not name:
                    continue
                occurrences.append((path, name, rest))
                freq[name] += 1

        if not occurrences:
            out("OK: scanned 0 url tags; no templates matched.")
            return

        top_names = {n for n, _c in freq.most_common(max(0, top_n))}

        def tokenize_rest(rest: str) -> list[str]:
            # Strip comments-ish, normalize whitespace.
            s = (rest or "").strip()
            if not s:
                return []
            return [t for t in re.split(r"\s+", s) if t]

        def count_positional_args(tokens: list[str]) -> int:
            # Stop at 'as'. Ignore kwargs (foo=bar). Count remaining positional tokens.
            count = 0
            for t in tokens:
                if t == "as":
                    break
                if "=" in t:
                    # kwarg style; do not count (best-effort)
                    continue
                count += 1
            return count

        def expected_arg_counts(name: str) -> set[int] | None:
            """Best-effort extraction of positional arg counts for a url name."""
            try:
                entries = resolver.reverse_dict.getlist(name)
            except Exception:
                return None
            counts: set[int] = set()
            for e in entries:
                # Django's reverse_dict entries are internal; try to infer param-list length.
                # We look for a list/tuple of parameter names among tuple elements.
                if isinstance(e, (list, tuple)):
                    for part in e:
                        if isinstance(part, (list, tuple)) and part and all(isinstance(x, str) for x in part):
                            counts.add(len(part))
            return counts or None

        # Pass 2: validate existence and (for top N) obvious arg-count mismatches.
        for path, name, rest in occurrences:
            total += 1

            if name not in reverse_keys:
                fallback = name.split(":")[-1] if ":" in name else None
                if fallback and fallback in reverse_keys:
                    warnings += 1
                    out(
                        f"WARN: {path.relative_to(templates_dir)} uses '{name}' (namespace not found, fallback '{fallback}' exists)."
                    )
                    continue

                missing += 1
                out(f"FAIL: {path.relative_to(templates_dir)} references unknown url name '{name}'.")
                if fail_fast:
                    raise SystemExit(2)
                continue

            # Only do arg-count heuristics for the top N most-used names.
            if name not in top_names:
                continue

            tokens = tokenize_rest(rest)
            used_count = count_positional_args(tokens)

            # If tag uses kwargs, our positional count may be incomplete; do not enforce.
            if any("=" in t for t in tokens):
                continue

            expected = expected_arg_counts(name)
            if expected is None:
                continue

            # If used_count doesn't match any expected counts, warn. This catches obvious issues.
            if used_count not in expected:
                warnings += 1
                out(
                    f"WARN: {path.relative_to(templates_dir)} url '{name}' uses {used_count} positional arg(s); expected one of {sorted(expected)}."
                )

        if missing:
            raise SystemExit(2)

        if warnings:
            out(f"OK (with warnings): scanned {total} url tags; {warnings} warnings.")
        else:
            out(f"OK: scanned {total} url tags; no missing names found.")
