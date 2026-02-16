from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from companies.decorators import require_min_role
from companies.models import EmployeeRole

from .forms import CatalogItemForm
from .models import CatalogItem, CatalogItemType


@require_min_role(EmployeeRole.MANAGER)
def catalog_item_list(request: HttpRequest) -> HttpResponse:
    company = request.active_company
    q = (request.GET.get("q") or "").strip()
    item_type = (request.GET.get("type") or "").strip()

    qs = CatalogItem.objects.filter(company=company, deleted_at__isnull=True).order_by("name")
    if item_type in {CatalogItemType.SERVICE, CatalogItemType.PRODUCT}:
        qs = qs.filter(item_type=item_type)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

    ctx = {
        "items": qs,
        "q": q,
        "type": item_type,
        "CatalogItemType": CatalogItemType,
    }
    return render(request, "catalog/catalogitem_list.html", ctx)


@require_min_role(EmployeeRole.MANAGER)
def catalog_item_create(request: HttpRequest) -> HttpResponse:
    company = request.active_company
    if request.method == "POST":
        form = CatalogItemForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Catalog item created.")
            return redirect("catalog:item_list")
    else:
        form = CatalogItemForm()

    return render(request, "catalog/catalogitem_form.html", {"form": form, "mode": "create"})


@require_min_role(EmployeeRole.MANAGER)
def catalog_item_edit(request: HttpRequest, pk: int) -> HttpResponse:
    company = request.active_company
    obj = get_object_or_404(CatalogItem, pk=pk, company=company, deleted_at__isnull=True)

    if request.method == "POST":
        form = CatalogItemForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Catalog item updated.")
            return redirect("catalog:item_list")
    else:
        form = CatalogItemForm(instance=obj)

    return render(request, "catalog/catalogitem_form.html", {"form": form, "mode": "edit", "object": obj})


@require_min_role(EmployeeRole.MANAGER)
def catalog_item_delete(request: HttpRequest, pk: int) -> HttpResponse:
    company = request.active_company
    obj = get_object_or_404(CatalogItem, pk=pk, company=company, deleted_at__isnull=True)

    if request.method == "POST":
        obj.soft_delete()
        messages.success(request, "Catalog item removed.")
        return redirect("catalog:item_list")

    return render(request, "catalog/catalogitem_delete.html", {"object": obj})
