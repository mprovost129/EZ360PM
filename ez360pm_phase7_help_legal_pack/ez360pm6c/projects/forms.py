from __future__ import annotations

import re
from django import forms
from django.forms import inlineformset_factory

from .models import Project, ProjectService, ProjectBillingType, ProjectFile

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

    class Meta:
        model = Project
        fields = [
            'client','assigned_to','project_number','name','description',
            'date_received','due_date','billing_type','flat_fee_cents','hourly_rate_cents',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'date_received': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = 'form-control'
            if isinstance(field.widget, forms.Select):
                css = 'form-select'
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' ' + css).strip()
        self.fields['billing_type'].widget = forms.Select(choices=ProjectBillingType.choices)
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
        if commit:
            obj.save()
            self.save_m2m()
        return obj


ProjectServiceFormSet = inlineformset_factory(
    Project,
    ProjectService,
    fields=['name','notes'],
    extra=3,
    can_delete=True,
    widgets={'notes': forms.Textarea(attrs={'rows': 2})},
)



class ProjectFileForm(forms.ModelForm):
    file_s3_key = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = ProjectFile
        fields = ["title", "file", "file_s3_key", "notes"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional title"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional notes"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs.update({"class": "form-control"})
