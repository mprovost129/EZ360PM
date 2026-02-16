from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django import forms
import decimal
from django.forms import inlineformset_factory

from core.forms.money import MoneyCentsField

from companies.models import Company
from crm.models import Client
from projects.models import Project
from .models import Document, DocumentLineItem, DocumentTemplate, DocumentType, DocumentStatus, NumberingScheme


class DocumentWizardForm(forms.Form):
    MODE_CHOICES = (
        ("new", "New"),
        ("copy", "Copy recent"),
    )

    mode = forms.ChoiceField(choices=MODE_CHOICES, initial="new")
    template = forms.ModelChoiceField(queryset=DocumentTemplate.objects.none(), required=False)
    copy_from = forms.ModelChoiceField(queryset=Document.objects.none(), required=False)

    def __init__(self, *, company: Company, doc_type: str, **kwargs):
        super().__init__(**kwargs)
        self.fields["template"].queryset = DocumentTemplate.objects.filter(
            company=company, doc_type=doc_type, is_active=True, deleted_at__isnull=True
        ).order_by("name")
        self.fields["copy_from"].queryset = Document.objects.filter(
            company=company, doc_type=doc_type, deleted_at__isnull=True
        ).order_by("-created_at")[:50]


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            "client",
            "project",
            "title",
            "description",
            "issue_date",
            "due_date",
            "valid_until",
            "notes",
            "status",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, company: Company, doc_type: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(company=company, deleted_at__isnull=True).order_by(
            "company_name", "last_name", "first_name"
        )
        self.fields["project"].queryset = Project.objects.filter(company=company, deleted_at__isnull=True).order_by(
            "-created_at"
        )

        # hide irrelevant date fields
        if doc_type == DocumentType.INVOICE:
            self.fields["valid_until"].required = False
        else:
            self.fields["due_date"].required = False

        # status choices per doc_type
        if doc_type in {DocumentType.ESTIMATE, DocumentType.PROPOSAL}:
            self.fields["status"].choices = [
                (DocumentStatus.DRAFT, "Draft"),
                (DocumentStatus.SENT, "Sent"),
                (DocumentStatus.ACCEPTED, "Accepted"),
                (DocumentStatus.DECLINED, "Declined"),
                (DocumentStatus.VOID, "Void"),
            ]
        else:
            self.fields["status"].choices = [
                (DocumentStatus.DRAFT, "Draft"),
                (DocumentStatus.SENT, "Sent"),
                (DocumentStatus.PARTIALLY_PAID, "Partially Paid"),
                (DocumentStatus.PAID, "Paid"),
                (DocumentStatus.VOID, "Void"),
            ]


class LineItemForm(forms.ModelForm):
    unit_price_cents = MoneyCentsField(required=False)
    tax_cents = MoneyCentsField(required=False)

    class Meta:
        model = DocumentLineItem
        fields = ["sort_order", "catalog_item", "name", "description", "qty", "unit_price_cents", "is_taxable", "tax_cents"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 1}),
        }

    def __init__(self, *args, **kwargs):
        company_default_taxable = bool(kwargs.pop("company_default_taxable", False))
        super().__init__(*args, **kwargs)

        # Sensible defaults for new rows
        if not self.instance.pk and not self.is_bound:
            self.fields["is_taxable"].initial = company_default_taxable


    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get("qty") or Decimal("0")
        unit_cents = int(cleaned.get("unit_price_cents") or 0)
        tax_cents = int(cleaned.get("tax_cents") or 0)

        # Compute totals (stored in cents)
        line_sub = int(qty * unit_cents)
        line_total = line_sub + tax_cents

        self.instance.unit_price_cents = unit_cents
        self.instance.tax_cents = tax_cents
        self.instance.line_subtotal_cents = line_sub
        self.instance.line_total_cents = line_total
        self.instance.name = cleaned.get("name") or (self.instance.catalog_item.name if self.instance.catalog_item else "")
        return cleaned


DocumentLineItemFormSet = inlineformset_factory(
    Document,
    DocumentLineItem,
    form=LineItemForm,
    extra=1,
    can_delete=True,
)


class NumberingSchemeForm(forms.ModelForm):
    class Meta:
        model = NumberingScheme
        fields = ["invoice_pattern", "estimate_pattern", "proposal_pattern"]
        help_texts = {
            "invoice_pattern": "Tokens: {YY} {YYYY} {MM} {DD} {SEQ:n}",
            "estimate_pattern": "Tokens: {YY} {YYYY} {MM} {DD} {SEQ:n}",
            "proposal_pattern": "Tokens: {YY} {YYYY} {MM} {DD} {SEQ:n}",
        }



class CreditNoteForm(forms.Form):
    number = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    subtotal = forms.DecimalField(
        required=True,
        max_digits=12,
        decimal_places=2,
        min_value=decimal.Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    tax = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=decimal.Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    total = forms.DecimalField(
        required=True,
        max_digits=12,
        decimal_places=2,
        min_value=decimal.Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def clean(self):
        cleaned = super().clean()
        subtotal = cleaned.get("subtotal") or decimal.Decimal("0.00")
        tax = cleaned.get("tax") or decimal.Decimal("0.00")
        total = cleaned.get("total") or decimal.Decimal("0.00")

        if total <= 0:
            raise forms.ValidationError("Total must be greater than $0.00.")

        # Enforce subtotal + tax == total within 1 cent
        expected = (subtotal + tax).quantize(decimal.Decimal("0.01"))
        total_q = total.quantize(decimal.Decimal("0.01"))
        if expected != total_q:
            raise forms.ValidationError("Subtotal + Tax must equal Total.")
        return cleaned

    @staticmethod
    def dollars_to_cents(val: decimal.Decimal) -> int:
        q = (val or decimal.Decimal("0.00")).quantize(decimal.Decimal("0.01"))
        return int(q * 100)

    def to_model_values(self) -> dict:
        cleaned = self.cleaned_data
        return {
            "number": (cleaned.get("number") or "").strip(),
            "subtotal_cents": self.dollars_to_cents(cleaned.get("subtotal")),
            "tax_cents": self.dollars_to_cents(cleaned.get("tax") or decimal.Decimal("0.00")),
            "total_cents": self.dollars_to_cents(cleaned.get("total")),
            "reason": cleaned.get("reason") or "",
        }

