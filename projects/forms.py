from __future__ import annotations

import re
from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory
from django.conf import settings

from core.forms.money import MoneyCentsField

from .models import Project, ProjectService, ProjectBillingType, ProjectFile
from catalog.models import CatalogItem, CatalogItemType
from crm.models import Client
from companies.models import EmployeeProfile

_DUR_RE = re.compile(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*$", re.I)


def parse_duration_to_minutes(raw: str) -> int:
    raw = (raw or '').strip()
    if not raw:
        return 0
    if ':' in raw:
        h, m = raw.split(':', 1)
        return int(h or 0) * 60 + int(m or 0)
    m = _DUR_RE.match(raw)
    if m:
        h = int(m.group(1) or 0)
        mm = int(m.group(2) or 0)
        return h * 60 + mm
    if raw.isdigit():
        return int(raw)
    raise forms.ValidationError('Enter estimated hours like 2h 30m, 2:30, or minutes.')


class ProjectForm(forms.ModelForm):
    estimated_hours = forms.CharField(required=False, help_text='e.g. 10h 30m')
    hourly_rate_cents = MoneyCentsField(required=False)
    flat_fee_cents = MoneyCentsField(required=False)

    class Meta:
        model = Project
        fields = [
            'client','assigned_to','project_number','name','description',
            'date_received','due_date','billing_type','hourly_rate_cents','flat_fee_cents',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'date_received': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = 'form-control'
            if isinstance(field.widget, forms.Select):
                css = 'form-select'
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' ' + css).strip()
        self.fields['billing_type'].widget = forms.Select(choices=ProjectBillingType.choices)

        # Company-scoped dropdowns
        if self.company is not None:
            # Client dropdown should only show clients for the active company.
            self.fields["client"].queryset = (
                Client.objects.filter(company=self.company, deleted_at__isnull=True)
                .order_by("company_name", "last_name", "first_name")
            )

            # Assigned-to dropdown should only show employees for the active company.
            self.fields["assigned_to"].queryset = (
                EmployeeProfile.objects.filter(company=self.company, deleted_at__isnull=True)
                .select_related("user")
                .order_by("user__last_name", "user__first_name", "user__email")
            )

        # In UI dropdowns we want the client label only (not "(Company)")
        # because the list is already company-scoped.
        if "client" in self.fields:
            self.fields["client"].label_from_instance = lambda obj: obj.display_label()

        if self.instance and getattr(self.instance, 'estimated_minutes', 0):
            mins = int(self.instance.estimated_minutes or 0)
            self.fields['estimated_hours'].initial = f"{mins//60}h {mins%60:02d}m"

    def clean(self):
        cleaned = super().clean()
        mins = parse_duration_to_minutes(cleaned.get('estimated_hours') or '')
        cleaned['estimated_minutes'] = mins
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.estimated_minutes = parse_duration_to_minutes(self.cleaned_data.get('estimated_hours') or '')
        obj.hourly_rate_cents = int(self.cleaned_data.get('hourly_rate_cents') or 0)
        obj.flat_fee_cents = int(self.cleaned_data.get('flat_fee_cents') or 0)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class ProjectServiceForm(forms.ModelForm):
    class Meta:
        model = ProjectService
        fields = ["catalog_item", "name", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)

        # Bootstrap styling
        for name, field in self.fields.items():
            css = "form-control"
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing + " " + css).strip()

        # Catalog service dropdown (company-scoped)
        qs = CatalogItem.objects.none()
        if self.company:
            qs = CatalogItem.objects.filter(
                company=self.company,
                item_type=CatalogItemType.SERVICE,
                is_active=True,
                deleted_at__isnull=True,
            ).order_by("name")
        self.fields["catalog_item"].queryset = qs
        self.fields["catalog_item"].required = False
        self.fields["name"].required = False
        self.fields["name"].widget.attrs.setdefault("placeholder", "Custom service name (optional)")

    def clean(self):
        cleaned = super().clean()
        catalog_item = cleaned.get("catalog_item")
        name = (cleaned.get("name") or "").strip()
        if not catalog_item and not name:
            # allow fully empty rows (inline formset extras)
            return cleaned
        if catalog_item:
            cleaned["name"] = catalog_item.name
        else:
            cleaned["name"] = name
        return cleaned


ProjectServiceFormSet = inlineformset_factory(
    Project,
    ProjectService,
    form=ProjectServiceForm,
    fields=['catalog_item','name','notes'],
    extra=3,
    can_delete=True,
    widgets={'notes': forms.Textarea(attrs={'rows': 2})},
)



class ProjectFileForm(forms.ModelForm):
    file_s3_key = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = ProjectFile
        fields = ["title", "file", "notes", "file_s3_key"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional title"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional notes"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        if getattr(settings, "USE_S3", False) and getattr(settings, "S3_DIRECT_UPLOADS", False):
            # In direct-upload mode, the browser uploads to S3 and submits only the object key.
            self.fields["file"].required = False

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("file") and cleaned.get("file_s3_key"):
            # OK: direct upload flow
            return cleaned
        return cleaned
