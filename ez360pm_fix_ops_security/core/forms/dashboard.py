from __future__ import annotations

from typing import Any

from django import forms

from billing.services import plan_meets
from companies.permissions import has_min_role

from billing.models import PlanCode

from core.dashboard_registry import get_dashboard_widgets


class DashboardLayoutForm(forms.Form):
    """Premium dashboard customization form (v1)."""

    def __init__(
        self,
        *,
        plan: str,
        employee_role: str,
        initial_layout: dict[str, list[str]] | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)

        widgets = get_dashboard_widgets()
        allowed_keys: list[str] = []
        for key, w in widgets.items():
            if not plan_meets(plan, min_plan=w.min_plan):
                continue
            if not has_min_role(type("E", (), {"role": employee_role})(), w.min_role):
                continue
            allowed_keys.append(key)

        # Build a stable initial order from current layout (if any)
        initial_layout = initial_layout or {"left": [], "right": []}
        left = [k for k in initial_layout.get("left", []) if k in allowed_keys]
        right = [k for k in initial_layout.get("right", []) if k in allowed_keys]
        remaining = [k for k in allowed_keys if k not in set(left + right)]
        # Put remaining keys into their default columns
        for k in remaining:
            if widgets[k].default_column == "left":
                left.append(k)
            else:
                right.append(k)

        # Render controls for each widget
        column_choices = [("left", "Left column"), ("right", "Right column")]

        def _index_map(keys: list[str]) -> dict[str, int]:
            return {k: i + 1 for i, k in enumerate(keys)}

        left_index = _index_map(left)
        right_index = _index_map(right)

        for key in allowed_keys:
            w = widgets[key]

            enabled_initial = key in left or key in right
            column_initial = "left" if key in left else ("right" if key in right else w.default_column)
            order_initial = left_index.get(key) or right_index.get(key) or 999

            self.fields[f"{key}__enabled"] = forms.BooleanField(
                required=False,
                initial=enabled_initial,
                label=w.label,
            )
            self.fields[f"{key}__column"] = forms.ChoiceField(
                required=True,
                choices=column_choices,
                initial=column_initial,
                label="Column",
            )
            self.fields[f"{key}__order"] = forms.IntegerField(
                required=True,
                min_value=1,
                max_value=99,
                initial=order_initial,
                label="Order",
                help_text="Lower numbers appear higher on the page.",
            )

        self.allowed_widget_keys = allowed_keys


    def build_layout_json(self) -> dict[str, list[str]]:
        widgets = get_dashboard_widgets()

        left_items: list[tuple[int, str]] = []
        right_items: list[tuple[int, str]] = []

        for key in getattr(self, "allowed_widget_keys", []):
            enabled = bool(self.cleaned_data.get(f"{key}__enabled"))
            if not enabled:
                continue
            column = str(self.cleaned_data.get(f"{key}__column") or widgets[key].default_column)
            order = int(self.cleaned_data.get(f"{key}__order") or widgets[key].default_order)
            if column == "left":
                left_items.append((order, key))
            else:
                right_items.append((order, key))

        left = [k for _, k in sorted(left_items, key=lambda t: (t[0], t[1]))]
        right = [k for _, k in sorted(right_items, key=lambda t: (t[0], t[1]))]

        # Ensure we always show the basics on Premium too.
        required = ["kpis", "quick_actions"]
        for r in required:
            if r not in left and r not in right:
                left.insert(0, r)

        return {"left": left, "right": right}
