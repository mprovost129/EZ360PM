from django.shortcuts import render

def index(request):
    """
    Public Help Center FAQ.
    Both logged-out and logged-in users can access.
    """
    sections = [
        {
            "slug": "getting-started",
            "title": "Getting Started",
            "items": [
                {"q": "How do I create my first project?",
                 "a": "Go to <em>Projects</em> → <em>New Project</em>, then fill in name, client, and budget."},
                {"q": "How do I invite a team member?",
                 "a": "Go to <em>Company</em> → <em>Team</em> → <em>Invite</em>, and enter their email."},
            ],
        },
        {
            "slug": "billing",
            "title": "Billing & Subscriptions",
            "items": [
                {"q": "How do I pick a plan?",
                 "a": "Open <em>Plans</em> under Billing and choose the tier that fits."},
                {"q": "How do I cancel or change my plan?",
                 "a": "Use the <em>Customer Portal</em> from the Plans page."},
            ],
        },
        {
            "slug": "invoices",
            "title": "Invoices & Payments",
            "items": [
                {"q": "How do I email an invoice?",
                 "a": "Open an invoice and click <em>Email</em>."},
                {"q": "How do I record a payment?",
                 "a": "Open an invoice and click <em>Add Payment</em>."},
            ],
        },
    ]
    return render(request, "helpcenter/index.html", {"sections": sections})
