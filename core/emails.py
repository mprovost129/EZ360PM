# core/emails.py
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

def send_invoice_email(inv, to_email: str, *, note: str = "", mode: str = "initial") -> int:
    # mode: "initial" or "reminder"
    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "[EZ360PM] ")
    if mode == "reminder":
        subject = f"{prefix}Reminder: Invoice {inv.number} from {inv.company.name}"
    else:
        subject = f"{prefix}Invoice {inv.number} from {inv.company.name}"

    ctx = {
        "inv": inv,
        "note": note,
        "mode": mode,
        "APP_NAME": getattr(settings, "APP_NAME", "EZ360PM"),
        "site_url": getattr(settings, "SITE_URL", ""),
    }
    text_body = render_to_string("emails/invoice.txt", ctx)
    html_body = render_to_string("emails/invoice.html", ctx)

    msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [to_email])
    msg.attach_alternative(html_body, "text/html")

    # Optional PDF attach if you added a renderer
    try:
        from core.pdf import render_invoice_pdf # type: ignore
        pdf_bytes = render_invoice_pdf(inv)
        if pdf_bytes:
            msg.attach(f"invoice_{inv.number}.pdf", pdf_bytes, "application/pdf")
    except Exception:
        pass

    return msg.send()

def send_estimate_email(est, to_email: str, *, note: str = "", mode: str = "initial") -> int:
    """
    mode: "initial" | "reminder"
    """
    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "[EZ360PM] ")
    if mode == "reminder":
        subject = f"{prefix}Reminder: Estimate {est.number} from {est.company.name}"
    else:
        subject = f"{prefix}Estimate {est.number} from {est.company.name}"

    public_url = f"{settings.SITE_URL}{reverse('core:estimate_public', kwargs={'token': str(est.public_token)})}"

    ctx = {
        "est": est,
        "note": note,
        "mode": mode,
        "APP_NAME": getattr(settings, "APP_NAME", "EZ360PM"),
        "site_url": getattr(settings, "SITE_URL", ""),
        "public_url": public_url,
    }

    text_body = render_to_string("emails/estimate.txt", ctx)
    html_body = render_to_string("emails/estimate.html", ctx)

    msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [to_email])
    msg.attach_alternative(html_body, "text/html")

    # Optional: attach PDF if you have a renderer
    try:
        from core.pdf import render_estimate_pdf # type: ignore
        pdf_bytes = None
        try:
            pdf_bytes = render_estimate_pdf(est)
        except TypeError:
            pdf_bytes = render_estimate_pdf(est)
        if pdf_bytes:
            msg.attach(f"estimate_{est.number}.pdf", pdf_bytes, "application/pdf")
    except Exception:
        pass

    return msg.send()
