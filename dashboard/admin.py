from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.conf import settings

def send_suggestion_admin_email(s):
    subject = f"[{getattr(settings, 'APP_NAME', 'EZ360PM')}] New suggestion — {s.subject or '(none)'}"
    ctx = {"s": s}

    text_body = render_to_string("dashboard/email/suggestion.txt", ctx)
    html_body = render_to_string("dashboard/email/suggestion.html", ctx)

    to_emails = [e for _, e in getattr(settings, "ADMINS", [])] or [getattr(settings, "SUPPORT_EMAIL", "")]
    to_emails = [e for e in to_emails if e]  # drop empties

    if not to_emails:
        return 0

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=to_emails,
        reply_to=[s.email] if s.email else None,
        connection=get_connection(fail_silently=True),
    )
    email.attach_alternative(html_body, "text/html")
    return email.send()
