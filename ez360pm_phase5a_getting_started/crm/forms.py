from __future__ import annotations

import csv
from io import StringIO

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import Client, ClientPhone, ContactPhoneType


US_STATES = [
    ("", "—"),
    ("AL", "AL"),
    ("AK", "AK"),
    ("AZ", "AZ"),
    ("AR", "AR"),
    ("CA", "CA"),
    ("CO", "CO"),
    ("CT", "CT"),
    ("DE", "DE"),
    ("FL", "FL"),
    ("GA", "GA"),
    ("HI", "HI"),
    ("ID", "ID"),
    ("IL", "IL"),
    ("IN", "IN"),
    ("IA", "IA"),
    ("KS", "KS"),
    ("KY", "KY"),
    ("LA", "LA"),
    ("ME", "ME"),
    ("MD", "MD"),
    ("MA", "MA"),
    ("MI", "MI"),
    ("MN", "MN"),
    ("MS", "MS"),
    ("MO", "MO"),
    ("MT", "MT"),
    ("NE", "NE"),
    ("NV", "NV"),
    ("NH", "NH"),
    ("NJ", "NJ"),
    ("NM", "NM"),
    ("NY", "NY"),
    ("NC", "NC"),
    ("ND", "ND"),
    ("OH", "OH"),
    ("OK", "OK"),
    ("OR", "OR"),
    ("PA", "PA"),
    ("RI", "RI"),
    ("SC", "SC"),
    ("SD", "SD"),
    ("TN", "TN"),
    ("TX", "TX"),
    ("UT", "UT"),
    ("VT", "VT"),
    ("VA", "VA"),
    ("WA", "WA"),
    ("WV", "WV"),
    ("WI", "WI"),
    ("WY", "WY"),
]


class ClientForm(forms.ModelForm):
    state = forms.ChoiceField(choices=US_STATES, required=False)

    class Meta:
        model = Client
        fields = [
            "first_name",
            "last_name",
            "company_name",
            "email",
            "internal_note",
            "address1",
            "address2",
            "city",
            "state",
            "zip_code",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "internal_note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "address1": forms.TextInput(attrs={"class": "form-control"}),
            "address2": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "zip_code": forms.TextInput(attrs={"class": "form-control"}),
        }


class ClientPhoneForm(forms.ModelForm):
    class Meta:
        model = ClientPhone
        fields = ["phone_type", "number"]
        widgets = {
            "phone_type": forms.Select(attrs={"class": "form-select"}),
            "number": forms.TextInput(attrs={"class": "form-control", "placeholder": "(555) 555-5555"}),
        }


ClientPhoneFormSet = inlineformset_factory(
    Client,
    ClientPhone,
    form=ClientPhoneForm,
    fields=("phone_type", "number"),
    extra=1,
    can_delete=True,
)


class ClientImportForm(forms.Form):
    csv_file = forms.FileField(
        help_text="Upload a CSV file. Use export format for best results.",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )


class ClientImportUploadWizardForm(forms.Form):
    csv_file = forms.FileField(
        help_text="Upload a CSV file. You'll preview and map columns before importing.",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )


class ClientImportMapWizardForm(forms.Form):
    """Mapping form for the client import wizard.

    The view provides `csv_headers` at init time to populate dropdown choices.
    """

    DUPLICATE_POLICY_CHOICES = (
        ("skip", "Skip rows where email matches an existing client"),
        ("update", "Update existing clients when email matches"),
        ("create", "Always create new clients (may create duplicates)"),
    )

    duplicate_policy = forms.ChoiceField(
        choices=DUPLICATE_POLICY_CHOICES,
        initial="skip",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Controls what happens when a row's email already exists for this company.",
    )

    save_mapping = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Save this mapping for reuse.",
    )
    mapping_name = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. QuickBooks Export"}),
    )
    set_as_default = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Use this mapping by default for future imports.",
    )

    def __init__(self, *args, csv_headers: list[str], initial_mapping: dict[str, str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)

        # Choices: blank = skip, then each header
        choices = [("", "— Skip —")] + [(h, h) for h in csv_headers]

        def _add_field(name: str, label: str, help_text: str = ""):
            self.fields[name] = forms.ChoiceField(
                label=label,
                required=False,
                choices=choices,
                widget=forms.Select(attrs={"class": "form-select"}),
                help_text=help_text,
            )

        # Core identity
        _add_field("company_name", "Organization / Company")
        _add_field("first_name", "First name")
        _add_field("last_name", "Last name")
        _add_field("email", "Email")
        _add_field("phone1", "Phone")

        # Address
        _add_field("address1", "Address line 1")
        _add_field("address2", "Address line 2")
        _add_field("city", "City")
        _add_field("state", "State")
        _add_field("zip_code", "Postal / ZIP")

        # Notes
        _add_field("internal_note", "Notes")

        # Optional second phone fields if the customer has them
        _add_field("phone2", "Phone (secondary)")
        _add_field("phone2_type", "Phone 2 type")
        _add_field("phone1_type", "Phone 1 type")

        # Apply defaults
        if initial_mapping:
            for k, v in initial_mapping.items():
                if k in self.fields:
                    self.fields[k].initial = v

    def cleaned_mapping(self) -> dict[str, str]:
        """Return destination_field -> source_header mappings, excluding blanks."""
        mapping: dict[str, str] = {}
        for key in [
            "company_name",
            "first_name",
            "last_name",
            "email",
            "phone1",
            "address1",
            "address2",
            "city",
            "state",
            "zip_code",
            "internal_note",
            "phone1_type",
            "phone2",
            "phone2_type",
        ]:
            val = (self.cleaned_data.get(key) or "").strip()
            if val:
                mapping[key] = val
        return mapping

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("save_mapping"):
            name = (cleaned.get("mapping_name") or "").strip()
            if not name:
                self.add_error("mapping_name", "Provide a name to save this mapping.")
        return cleaned


CLIENT_EXPORT_FIELDS = [
    "company_name",
    "first_name",
    "last_name",
    "email",
    "internal_note",
    "address1",
    "address2",
    "city",
    "state",
    "zip_code",
    "phone1",
    "phone1_type",
    "phone2",
    "phone2_type",
]


def _normalize_state_value(raw: str) -> str:
    """Normalize state inputs to a 2-letter US abbreviation when possible.

    Accepts:
    - 2-letter abbreviations (MA, RI, etc.)
    - Full state names (Massachusetts, Rhode Island, etc.)
    """
    raw = (raw or "").strip()
    if not raw:
        return ""

    # If already an abbreviation, normalize casing.
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()

    # Map full state names -> abbreviations using US_STATES choices.
    name_to_abbr = {label.lower(): abbr for (abbr, label) in US_STATES if abbr and label}
    abbr = name_to_abbr.get(raw.lower(), "")
    return abbr.upper() if abbr else ""


def _normalize_zip(raw: str) -> str:
    """Normalize ZIP/postal inputs (e.g., '2766.0' -> '02766' when possible)."""
    s = (raw or "").strip()
    if not s:
        return ""

    # Strip trailing .0 produced by some exports
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]

    # Keep leading zeros if present, otherwise attempt to left-pad 5-digit US zips when obviously missing.
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 4:  # common MA/RI issue when leading 0 is dropped
        return digits.zfill(5)
    if len(digits) == 5:
        return digits
    # If it's ZIP+4 or non-US, return as-is
    return s


def _normalize_email(raw: str) -> str:
    s = (raw or "").strip().lower()
    # Some exports include multiple emails in one cell; take the first.
    if "," in s:
        s = s.split(",", 1)[0].strip()
    if ";" in s:
        s = s.split(";", 1)[0].strip()
    return s


def _normalize_phone(raw: str) -> str:
    """Normalize phone numbers for dedupe/storage.

    Strategy:
    - Keep digits only
    - If 11 digits starting with 1, drop leading country code
    - If 10 digits, format as (XXX) XXX-XXXX
    - Otherwise, return trimmed raw
    """
    s = (raw or "").strip()
    if not s:
        return ""
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
    # Keep original if it doesn't look like a US number
    return s


def parse_client_csv(content: str) -> list[dict[str, str]]:
    """Parse CSV content and map common column headers to EZ360PM client import keys.

    Canonical keys expected by the importer (crm.views.client_import):
      company_name, first_name, last_name, email, internal_note,
      address1, address2, city, state, zip_code,
      phone1, phone1_type, phone2, phone2_type
    """
    if not content.strip():
        raise ValidationError("Empty CSV file.")

    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames:
        raise ValidationError("CSV must have a header row.")

    # Header mapping: incoming header -> canonical key
    header_map = {
        # Your CSV (example export)
        "Organization": "company_name",
        "First Name": "first_name",
        "Last Name": "last_name",
        "Email": "email",
        "Phone": "phone1",
        "Address Line 1": "address1",
        "Address Line 2": "address2",
        "City": "city",
        "Province/State": "state",
        "Postal Code": "zip_code",
        "Notes": "internal_note",
        # Common alternates
        "Company": "company_name",
        "Company Name": "company_name",
        "First": "first_name",
        "Last": "last_name",
        "E-mail": "email",
        "Email Address": "email",
        "Mobile": "phone1",
        "Phone 1": "phone1",
        "Phone1": "phone1",
        "Phone 1 Type": "phone1_type",
        "Phone1 Type": "phone1_type",
        "Phone 2": "phone2",
        "Phone2": "phone2",
        "Phone 2 Type": "phone2_type",
        "Phone2 Type": "phone2_type",
        "Address1": "address1",
        "Address 1": "address1",
        "Address2": "address2",
        "Address 2": "address2",
        "State": "state",
        "ZIP": "zip_code",
        "Zip": "zip_code",
        "Zip Code": "zip_code",
        "Postal": "zip_code",
        "PostalCode": "zip_code",
        "Note": "internal_note",
        "Internal Note": "internal_note",
    }

    rows: list[dict[str, str]] = []
    for raw in reader:
        # Normalize raw keys/values
        cleaned = {str(k or "").strip(): str(v or "").strip() for k, v in raw.items()}
        if not any(cleaned.values()):
            continue

        out: dict[str, str] = {}

        # Apply header mapping
        for k, v in cleaned.items():
            if not k:
                continue
            canonical = header_map.get(k, None)
            if canonical:
                out[canonical] = v
            else:
                # allow already-canonical headers through unchanged
                out[k.strip()] = v

        # Post-normalization for common fields
        out["state"] = _normalize_state_value(out.get("state", ""))
        out["zip_code"] = _normalize_zip(out.get("zip_code", ""))
        out["email"] = _normalize_email(out.get("email", ""))
        out["phone1"] = _normalize_phone(out.get("phone1", ""))
        out["phone2"] = _normalize_phone(out.get("phone2", ""))

        # If Organization is blank but we have a person name, keep company_name blank (OK).
        # If company_name is present but first/last are empty, still import (OK).

        rows.append(out)

    if not rows:
        raise ValidationError("No rows found in CSV.")

    return rows


def suggest_client_mapping(csv_headers: list[str]) -> dict[str, str]:
    """Suggest a destination_field -> source_header mapping.

    This is used by the import wizard to pre-select sensible defaults.
    """

    incoming_to_canonical = {
        # Your CSV (example export)
        "Organization": "company_name",
        "First Name": "first_name",
        "Last Name": "last_name",
        "Email": "email",
        "Phone": "phone1",
        "Address Line 1": "address1",
        "Address Line 2": "address2",
        "City": "city",
        "Province/State": "state",
        "Postal Code": "zip_code",
        "Notes": "internal_note",
        # Common alternates
        "Company": "company_name",
        "Company Name": "company_name",
        "First": "first_name",
        "Last": "last_name",
        "E-mail": "email",
        "Email Address": "email",
        "Mobile": "phone1",
        "Phone 1": "phone1",
        "Phone1": "phone1",
        "Phone 1 Type": "phone1_type",
        "Phone1 Type": "phone1_type",
        "Phone 2": "phone2",
        "Phone2": "phone2",
        "Phone 2 Type": "phone2_type",
        "Phone2 Type": "phone2_type",
        "Address1": "address1",
        "Address 1": "address1",
        "Address2": "address2",
        "Address 2": "address2",
        "State": "state",
        "ZIP": "zip_code",
        "Zip": "zip_code",
        "Zip Code": "zip_code",
        "Postal": "zip_code",
        "PostalCode": "zip_code",
        "Note": "internal_note",
        "Internal Note": "internal_note",
    }

    suggested: dict[str, str] = {}

    # Prefer exact header matches first
    for h in csv_headers:
        canonical = incoming_to_canonical.get(h)
        if canonical and canonical not in suggested:
            suggested[canonical] = h

    # Also handle already-canonical header names
    canonical_fields = {
        "company_name",
        "first_name",
        "last_name",
        "email",
        "phone1",
        "phone1_type",
        "phone2",
        "phone2_type",
        "address1",
        "address2",
        "city",
        "state",
        "zip_code",
        "internal_note",
    }
    for h in csv_headers:
        if h in canonical_fields and h not in suggested:
            suggested[h] = h

    return suggested


def normalize_phone_type(raw: str) -> str:
    raw = (raw or "").strip().lower()
    allowed = {c[0] for c in ContactPhoneType.choices}
    if raw in allowed:
        return raw
    # accept common labels
    if raw in {"cell", "mobile"}:
        return ContactPhoneType.MOBILE
    if raw in {"work", "office"}:
        return ContactPhoneType.WORK
    if raw in {"home"}:
        return ContactPhoneType.HOME
    return ContactPhoneType.OTHER


# Public normalization helpers (used by import wizards)
def normalize_state(raw: str) -> str:
    return _normalize_state_value(raw)


def normalize_zip(raw: str) -> str:
    return _normalize_zip(raw)


def normalize_email(raw: str) -> str:
    return _normalize_email(raw)


def normalize_phone(raw: str) -> str:
    return _normalize_phone(raw)


def normalize_text(raw: str) -> str:
    # Trim and collapse whitespace
    s = (raw or "").replace("\u00a0", " ")
    s = " ".join(s.split())
    return s.strip()
