from __future__ import annotations

from dataclasses import dataclass

from billing.models import PlanCode


@dataclass(frozen=True)
class DashboardWidget:
    key: str
    label: str
    min_plan: str
    min_role: str
    default_column: str
    default_order: int


def get_dashboard_widgets() -> dict[str, DashboardWidget]:
    """Registry of widgets available on the dashboard."""

    # NOTE: Role comparisons are enforced elsewhere (template + decorators).
    # This registry primarily drives customization UI and layout defaults.
    return {
        "kpis": DashboardWidget(
            key="kpis",
            label="KPI summary",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="left",
            default_order=10,
        ),

        # --- Activity / Operations ---
        "recent_invoices": DashboardWidget(
            key="recent_invoices",
            label="Recent invoices",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="left",
            default_order=20,
        ),
        "quick_actions": DashboardWidget(
            key="quick_actions",
            label="Quick actions",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            # Prefer quick actions in the right rail so the dashboard reads like a
            # report on the left with actions always available.
            default_column="right",
            default_order=5,
        ),
        "outstanding_invoices": DashboardWidget(
            key="outstanding_invoices",
            label="Outstanding invoices (due date)",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            # Keep available for users who prefer it, but don't force it into the
            # default "premium" dashboard composition.
            default_column="right",
            default_order=30,
        ),
        "recent_open_projects": DashboardWidget(
            key="recent_open_projects",
            label="Recent open projects",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="left",
            default_order=30,
        ),

        # --- Premium dashboard visuals (available to all plans; safe + readonly) ---
        "revenue_trend": DashboardWidget(
            key="revenue_trend",
            label="Revenue trend (6 months)",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="left",
            default_order=40,
        ),
        "ar_aging": DashboardWidget(
            key="ar_aging",
            label="A/R aging",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="left",
            default_order=50,
        ),
        "recent_expenses": DashboardWidget(
            key="recent_expenses",
            label="Recent expenses",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="left",
            default_order=60,
        ),
        "getting_started": DashboardWidget(
            key="getting_started",
            label="Getting started checklist",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="right",
            default_order=70,
        ),
        "quick_notes": DashboardWidget(
            key="quick_notes",
            label="Quick notes",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="right",
            default_order=80,
        ),
        "premium_insights": DashboardWidget(
            key="premium_insights",
            label="Premium insights",
            min_plan=PlanCode.PREMIUM,
            min_role="manager",
            default_column="right",
            default_order=10,
        ),
        "payables": DashboardWidget(
            key="payables",
            label="Payables summary",
            min_plan=PlanCode.PROFESSIONAL,
            min_role="manager",
            default_column="right",
            default_order=20,
        ),
        "active_company": DashboardWidget(
            key="active_company",
            label="Active company",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="right",
            default_order=40,
        ),
        "your_role": DashboardWidget(
            key="your_role",
            label="Your role",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="right",
            default_order=50,
        ),
        "subscription": DashboardWidget(
            key="subscription",
            label="Subscription",
            min_plan=PlanCode.STARTER,
            min_role="staff",
            default_column="right",
            default_order=60,
        ),
    }


def default_dashboard_layout() -> dict[str, list[str]]:
    """Return the default dashboard composition.

    We intentionally keep the default dashboard lean and premium:

    LEFT column (main): KPIs + operational activity + core analytics.
    RIGHT column (rail): quick actions + onboarding (until complete) + quick notes.

    Other widgets remain available via Customize, but are not forced into the default.
    """

    return {
        "left": [
            "kpis",
            "recent_invoices",
            "recent_open_projects",
            "revenue_trend",
            "ar_aging",
        ],
        "right": [
            "quick_actions",
            "quick_notes",
            "getting_started",
        ],
    }
