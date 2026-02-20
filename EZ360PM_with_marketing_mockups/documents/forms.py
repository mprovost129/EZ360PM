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
            "number",
            "use_project_numbering",
            "client",
            "project",
            "title",
            "description",
            "issue_date",
            "due_date",
            "valid_until",
            "sales_tax_percent",
            "deposit_type",
            "deposit_value",
            "header_text",
            "notes",
            "footer_text",
            "terms",
            "status",
        ]
        widgets = {
            "number": forms.TextInput(attrs={"placeholder": "Auto"}),
            "description": forms.Textarea(attrs={"rows": 2}),
            "header_text": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "footer_text": forms.Textarea(attrs={"rows": 2}),
            "terms": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, company: Company, doc_type: str, can_edit_number: bool = False, **kwargs):
        super().__init__(*args, **kwargs)

        # Bootstrap styling
        for name, field in self.fields.items():
            w = field.widget
            base_cls = w.attrs.get("class", "")
            if isinstance(w, forms.Select):
                w.attrs["class"] = (base_cls + " form-select").strip()
            elif isinstance(w, (forms.Textarea, forms.TextInput, forms.DateInput, forms.NumberInput)):
                w.attrs["class"] = (base_cls + " form-control").strip()

        # Tighter composer feel
        if "description" in self.fields:
            self.fields["description"].widget.attrs.setdefault("rows", 2)
        if "notes" in self.fields:
            self.fields["notes"].widget.attrs.setdefault("rows", 3)
        if "header_text" in self.fields:
            self.fields["header_text"].widget.attrs.setdefault("rows", 2)
        if "footer_text" in self.fields:
            self.fields["footer_text"].widget.attrs.setdefault("rows", 2)
        if "terms" in self.fields:
            self.fields["terms"].widget.attrs.setdefault("rows", 3)
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

        # Only invoices support project numbering toggle.
        if doc_type != DocumentType.INVOICE:
            self.fields.pop("use_project_numbering", None)

        # Number is always shown, but only editable when allowed.
        if "number" in self.fields:
            self.fields["number"].required = False
            if not can_edit_number:
                self.fields["number"].disabled = True

        if "use_project_numbering" in self.fields and not can_edit_number:
            # tie number + toggle together
            self.fields["use_project_numbering"].disabled = True

        # ------------------------------------------------------------------
        # Defaults / per-doc-type tweaks
        # ------------------------------------------------------------------

        # Defaults for composer fields (only when creating a new doc)
        if not self.instance.pk and not self.is_bound:
            try:
                self.fields["sales_tax_percent"].initial = getattr(company, "default_sales_tax_percent", 0) or 0
            except Exception:
                pass

        # Only invoices have deposit + terms; hide for proposals/estimates.
        if doc_type in {DocumentType.ESTIMATE, DocumentType.PROPOSAL}:
            if "deposit_type" in self.fields:
                self.fields["deposit_type"].required = False
            if "deposit_value" in self.fields:
                self.fields["deposit_value"].required = False
            if "terms" in self.fields:
                self.fields["terms"].required = False

        # Deposit value should look like money (no browser spinner).
        if "deposit_value" in self.fields:
            self.fields["deposit_value"].widget = forms.TextInput(
                attrs={
                    "class": "form-control text-end",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                    "autocomplete": "off",
                }
            )

        # status choices per doc_type
        if "status" in self.fields:
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

    def clean_number(self):
        val = (self.cleaned_data.get("number") or "").strip()
        # Allow blank (auto allocation)
        if not val:
            return ""

        # Disallow whitespace-only / overly long
        if len(val) > 40:
            raise forms.ValidationError("Number is too long.")

        # Uniqueness within company + doc_type (ignoring soft-deleted docs)
        try:
            company = getattr(self.instance, "company", None)
            doc_type = getattr(self.instance, "doc_type", None)
            if company and doc_type:
                qs = Document.objects.filter(company=company, doc_type=doc_type, number__iexact=val, deleted_at__isnull=True)
                if self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    raise forms.ValidationError("That number is already in use.")
        except Exception:
            # best-effort: don't break migrations/startup
            pass
        return val


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
        company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)

        # Bootstrap styling
        for name, field in self.fields.items():
            w = field.widget
            base_cls = w.attrs.get("class", "")
            if isinstance(w, forms.Select):
                w.attrs["class"] = (base_cls + " form-select form-select-sm").strip()
            elif isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = (base_cls + " form-check-input").strip()
            elif isinstance(w, (forms.Textarea, forms.TextInput, forms.NumberInput)):
                w.attrs["class"] = (base_cls + " form-control form-control-sm").strip()

        # Numeric inputs feel like money/qty
        if "qty" in self.fields:
            self.fields["qty"].widget.attrs.setdefault("step", "0.01")

        # Sort order is controlled by the UI (up/down). Keep hidden.
        if "sort_order" in self.fields:
            self.fields["sort_order"].widget = forms.HiddenInput()

        # Scope catalog dropdown to the active company
        if "catalog_item" in self.fields and company is not None:
            try:
                from catalog.models import CatalogItem

                self.fields["catalog_item"].queryset = CatalogItem.objects.filter(
                    company=company, is_active=True, deleted_at__isnull=True
                ).order_by("name")
            except Exception:
                pass

        # Sensible defaults for new rows
        if not self.instance.pk and not self.is_bound:
            self.fields["is_taxable"].initial = company_default_taxable

        # Document composer JS auto-fill endpoint base
        if "catalog_item" in self.fields:
            try:
                from django.urls import reverse

                self.fields["catalog_item"].widget.attrs.setdefault(
                    "data-catalog-json-base", reverse("catalog:item_json", args=[0])
                )
            except Exception:
                pass


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
        fields = [
            "invoice_pattern",
            "invoice_reset",
            "invoice_seq",
            "estimate_pattern",
            "estimate_reset",
            "estimate_seq",
            "proposal_pattern",
            "proposal_reset",
            "proposal_seq",
        ]
        widgets = {
            "invoice_pattern": forms.TextInput(attrs={"placeholder": "e.g., INV-{YY}{MM}-{SEQ:4}"}),
            "estimate_pattern": forms.TextInput(attrs={"placeholder": "e.g., EST-{YY}{MM}-{SEQ:4}"}),
            "proposal_pattern": forms.TextInput(attrs={"placeholder": "e.g., PRO-{YY}{MM}-{SEQ:4}"}),
            "invoice_seq": forms.NumberInput(attrs={"min": 1, "step": 1}),
            "estimate_seq": forms.NumberInput(attrs={"min": 1, "step": 1}),
            "proposal_seq": forms.NumberInput(attrs={"min": 1, "step": 1}),
        }
        help_texts = {
            "invoice_pattern": "Tokens: {YY} {YYYY} {MM} {DD} {SEQ:n}",
            "estimate_pattern": "Tokens: {YY} {YYYY} {MM} {DD} {SEQ:n}",
            "proposal_pattern": "Tokens: {YY} {YYYY} {MM} {DD} {SEQ:n}",
            "invoice_reset": "Optional: reset the SEQ counter monthly/yearly (for patterns like {YY}{MM}{SEQ:2}).",
            "estimate_reset": "Optional: reset the SEQ counter monthly/yearly.",
            "proposal_reset": "Optional: reset the SEQ counter monthly/yearly.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, (forms.TextInput, forms.NumberInput, forms.Select)):
                w.attrs["class"] = (w.attrs.get("class", "") + " form-control").strip()



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

class StatementEmailForm(forms.Form):
    TONE_CHOICES = (
        ('sent', 'Standard'),
        ('friendly', 'Friendly nudge'),
        ('past_due', 'Past due'),
    )

    to_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "client@email.com"}))
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    tone = forms.ChoiceField(
        required=False,
        choices=TONE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='sent',
    )
    attach_pdf = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Attach a PDF statement (requires WeasyPrint).",
    )

    email_me_copy = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Email me a copy of this statement.",
    )

    def __init__(self, *args, client: Client, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        if not self.is_bound:
            self.fields["to_email"].initial = (client.email or "").strip()

    def clean_to_email(self):
        val = (self.cleaned_data.get("to_email") or "").strip()
        if not val and not (self.client.email or "").strip():
            raise forms.ValidationError("Client has no email address. Enter an address to send to.")
        return val

    def clean_tone(self):
        val = (self.cleaned_data.get('tone') or 'sent').strip().lower()
        if val not in {'sent', 'friendly', 'past_due'}:
            val = 'sent'
        return val
