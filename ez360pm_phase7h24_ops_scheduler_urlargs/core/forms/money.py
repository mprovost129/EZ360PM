from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms


_CENTS = Decimal('100')


def parse_money_to_decimal(raw: object) -> Decimal:
    """Parse a money-like input to a Decimal dollars value (2dp).

    Accepts strings like "$1,234.56", "1234.56", "1234", etc.
    """
    if raw is None:
        return Decimal('0.00')
    if isinstance(raw, (int, float, Decimal)):
        try:
            return Decimal(str(raw)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            raise forms.ValidationError('Enter a valid amount.')

    s = str(raw).strip()
    if not s:
        return Decimal('0.00')
    # Strip common adornments
    s = s.replace('$', '').replace(',', '').strip()
    try:
        return Decimal(s).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise forms.ValidationError('Enter a valid amount (e.g. $12.34).')


class MoneyCentsField(forms.DecimalField):
    """A form field that *displays dollars* but returns an int cents value."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_digits', 12)
        kwargs.setdefault('decimal_places', 2)
        kwargs.setdefault('min_value', Decimal('0.00'))
        super().__init__(*args, **kwargs)

        # Reasonable UX defaults
        self.widget.attrs.setdefault('inputmode', 'decimal')
        self.widget.attrs.setdefault('placeholder', '$0.00')
        self.widget.attrs.setdefault('step', '0.01')

    def prepare_value(self, value):
        # Model may store cents as int
        if isinstance(value, int):
            return (Decimal(value) / _CENTS).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return super().prepare_value(value)

    def to_python(self, value):
        dollars = parse_money_to_decimal(value)
        # Convert to cents
        cents = int((dollars * _CENTS).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        return cents
