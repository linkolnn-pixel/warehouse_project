from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from rest_framework.generics import get_object_or_404

from inventory.decorators import test_mode_login_required
from inventory.forms import CustomerForm, SupplierForm
from inventory.models import Customer, Sale, Supplier


@test_mode_login_required
def supplier_create(request):
    next_name = request.GET.get("next", "products_catalog")
    selected_products = request.GET.getlist("products")
    return_url = request.GET.get("return_url")

    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            try:
                supplier.save()
                messages.success(request, f"Поставщик «{supplier.company_name}» создан.")

                url = reverse(next_name)

                params = [f"supplier={supplier.pk}"]

                for pid in selected_products:
                    params.append(f"products={pid}")

                if return_url:
                    params.append(f"return_url={return_url}")
                if params:
                    url += "?" + "&".join(params)

                return redirect(url)
            except IntegrityError:
                messages.error(request, "Такой поставщик уже существует.")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Ошибка [{field}]: {error}")
    else:
        form = SupplierForm()

    return render(request, "inventory/supplier_form.html", {"form": form})


@test_mode_login_required
def customer_create(request):
    next_name = request.GET.get("next", "sale_create")
    selected_products = request.GET.getlist("products")
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            try:
                customer.save()
                messages.success(
                    request,
                    f"Клиент «{customer.last_name} {customer.first_name}» создан.",
                )
                # Собираем все нужные параметры в словарь/список
                query_kwargs = [("customer", customer.pk)]
                for product_id in selected_products:
                    query_kwargs.append(("products", product_id))

                # Формируем URL
                url = reverse(next_name)
                if query_kwargs:
                    # urlencode сам правильно склеит всё через & и закодирует спецсимволы
                    url += "?" + urlencode(query_kwargs)
                return redirect(url)
            except IntegrityError:
                messages.error(request, "Такой клиент уже существует.")
    else:
        form = CustomerForm()
    return render(request, "inventory/customer_form.html", {"form": form})


@test_mode_login_required
def customers_list(request):
    customers = Customer.objects.order_by("last_name", "first_name")
    return render(request, "inventory/customers.html", {"customers": customers})


@test_mode_login_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    sales = (
        Sale.objects.filter(customer=customer)
        .annotate(
            annotated_total=Coalesce(
                Sum(
                    F("items__quantity") * F("items__sale_price"),
                    output_field=DecimalField(),
                ),
                Decimal("0.00"),
            )
        )
        .order_by("-date", "-id")
    )

    total_sales = sales.aggregate(total=Coalesce(Sum("annotated_total"), Decimal("0.00")))["total"]
    total_profit = sum(sale.net_profit for sale in sales) if sales else 0

    sales_count = sales.count()

    return render(
        request,
        "inventory/customer_detail.html",
        {
            "customer": customer,
            "sales": sales,
            "sales_count": sales_count,
            "total_sales": total_sales,
            "total_profit": total_profit,
        },
    )


@require_POST
def api_supplier_create(request):
    company_name = request.POST.get("company_name")
    inn = request.POST.get("inn", "")

    if not company_name:
        return JsonResponse({"error": "Введите название компании"}, status=400)

    obj = Supplier.objects.create(company_name=company_name, inn=inn)
    return JsonResponse({"id": obj.id, "name": obj.company_name})


@require_POST
def api_customer_create(request):
    first_name = request.POST.get("first_name", "")
    last_name = request.POST.get("last_name", "")

    if not first_name or not last_name:
        return JsonResponse({"error": "Имя и фамилия обязательны"}, status=400)

    obj = Customer.objects.create(first_name=first_name, last_name=last_name)
    return JsonResponse({"id": obj.id, "name": f"{last_name} {first_name}".strip()})
