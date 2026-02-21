from __future__ import annotations

import re

from expenses.models import Expense, Merchant

from .models import BankRule, BankTransaction


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def rule_matches(rule: BankRule, tx: BankTransaction) -> bool:
    if not rule.is_active:
        return False

    amt = int(tx.amount_cents or 0)
    if rule.min_amount_cents is not None and amt < int(rule.min_amount_cents):
        return False
    if rule.max_amount_cents is not None and amt > int(rule.max_amount_cents):
        return False

    target = tx.name if rule.match_field == BankRule.MatchField.NAME else tx.category
    hay = _norm(target)
    needle = _norm(rule.match_text)
    if not needle:
        return False

    if rule.match_type == BankRule.MatchType.CONTAINS:
        return needle in hay
    if rule.match_type == BankRule.MatchType.STARTS_WITH:
        return hay.startswith(needle)
    if rule.match_type == BankRule.MatchType.EQUALS:
        return hay == needle
    return False


def apply_rules_to_transaction(*, tx: BankTransaction, rules: list[BankRule]) -> bool:
    """Apply the first matching rule to a transaction.

    Returns True if a rule was applied.
    """

    if tx.status in {BankTransaction.Status.EXPENSE_CREATED}:
        return False

    for rule in rules:
        if not rule_matches(rule, tx):
            continue

        tx.applied_rule = rule

        # Always set suggestions when provided
        if rule.merchant_name:
            tx.suggested_merchant_name = rule.merchant_name
        if rule.expense_category:
            tx.suggested_category = rule.expense_category

        if rule.action == BankRule.Action.IGNORE:
            tx.status = BankTransaction.Status.IGNORED
        elif rule.action == BankRule.Action.TRANSFER:
            tx.status = BankTransaction.Status.TRANSFER
        elif rule.action == BankRule.Action.AUTO_CREATE_EXPENSE:
            # Only create expenses for debits (positive amounts)
            if int(tx.amount_cents) > 0 and tx.linked_expense_id is None:
                company = tx.account.connection.company
                employee = None
                merchant_name = (tx.suggested_merchant_name or tx.name or "").strip()[:160] or "Bank transaction"
                merchant, _ = Merchant.objects.get_or_create(company=company, name=merchant_name)
                exp = Expense.objects.create(
                    company=company,
                    created_by=employee,
                    merchant=merchant,
                    date=tx.posted_date,
                    category=(tx.suggested_category or tx.category or "")[:120],
                    description=f"Imported from bank feed: {tx.transaction_id}",
                    amount_cents=int(tx.amount_cents),
                    tax_cents=0,
                    total_cents=int(tx.amount_cents),
                    status="draft",
                )
                tx.linked_expense = exp
                tx.status = BankTransaction.Status.EXPENSE_CREATED
            else:
                tx.status = BankTransaction.Status.NEW
        else:
            # Suggest only
            tx.status = BankTransaction.Status.NEW

        tx.save(
            update_fields=[
                "status",
                "suggested_merchant_name",
                "suggested_category",
                "applied_rule",
                "linked_expense",
            ]
        )
        return True

    return False


def apply_rules_for_company(company, *, qs=None) -> int:
    """Apply active rules to NEW transactions for a company.

    Returns number of transactions updated.
    """

    rules = list(company.bank_rules.filter(is_active=True).order_by("priority", "id"))
    if not rules:
        return 0

    txs = qs if qs is not None else BankTransaction.objects.filter(account__connection__company=company)
    txs = txs.select_related("account__connection").filter(status=BankTransaction.Status.NEW)

    updated = 0
    for tx in txs[:500]:
        if apply_rules_to_transaction(tx=tx, rules=rules):
            updated += 1
    return updated
