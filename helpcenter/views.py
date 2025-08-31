from django.contrib.auth.decorators import login_required
from django.shortcuts import render

def index(request):
    """
    Public help directory. Logged out and logged in users can read it.
    """
    sections = [
        {"slug": "getting-started", "title": "Getting started", "items": [
            {"q": "Create your first project", "a": "Go to Projects → New Project…"},
            {"q": "Invite a team member", "a": "Company → Team → Invite…"},
        ]},
        {"slug": "billing", "title": "Billing & subscriptions", "items": [
            {"q": "Pick a plan", "a": "Open Plans and choose the tier that fits."},
            {"q": "Cancel or change plan", "a": "Use the Customer Portal from Plans."},
        ]},
        {"slug": "invoices", "title": "Invoices & payments", "items": [
            {"q": "Email an invoice", "a": "Open an invoice → Email."},
            {"q": "Record a payment", "a": "Open an invoice → Add payment."},
        ]},
    ]
    return render(request, "helpcenter/index.html", {"sections": sections})
