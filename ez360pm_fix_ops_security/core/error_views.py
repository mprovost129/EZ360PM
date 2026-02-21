from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import render


def error_404(request, exception):
    # Error templates must never raise, otherwise Django will recurse into 500.
    try:
        return render(request, "404.html", status=404)
    except Exception:
        return HttpResponse("<h1>Not found</h1>", status=404)


def error_500(request):
    # Error templates must never raise, otherwise Django will recurse.
    try:
        return render(request, "500.html", status=500)
    except Exception:
        return HttpResponse("<h1>Server error</h1>", status=500)
