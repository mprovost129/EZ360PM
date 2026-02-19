from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.db.models import Q

from companies.services import ensure_active_company_for_user, get_active_company
from notes.forms import UserNoteForm
from notes.models import UserNote


@login_required
def note_list(request: HttpRequest) -> HttpResponse:
    if not ensure_active_company_for_user(request):
        return redirect("companies:switch")

    company = get_active_company(request)
    qs = UserNote.objects.filter(company=company, created_by=request.user)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(subject__icontains=q)
            | Q(body__icontains=q)
            | Q(contact_name__icontains=q)
            | Q(contact_email__icontains=q)
            | Q(contact_phone__icontains=q)
        )

    notes = qs.select_related("company")[:200]

    ctx = {
        "company": company,
        "notes": notes,
        "q": q,
        "form": UserNoteForm(),
    }
    return render(request, "notes/note_list.html", ctx)


@login_required
def note_create(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("notes:list")

    if not ensure_active_company_for_user(request):
        return redirect("companies:switch")

    company = get_active_company(request)

    form = UserNoteForm(request.POST)
    if form.is_valid():
        obj: UserNote = form.save(commit=False)
        obj.company = company
        obj.created_by = request.user
        obj.save()
        messages.success(request, "Note saved.")
    else:
        messages.error(request, "Please fix the errors and try again.")

    nxt = (request.POST.get("next") or "").strip()
    if nxt:
        return redirect(nxt)
    return redirect("notes:list")
