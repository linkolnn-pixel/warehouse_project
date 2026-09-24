from decimal import Decimal
from urllib.parse import urlencode

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.urls import reverse
from rest_framework.generics import get_object_or_404

from inventory.decorators import test_mode_login_required
from inventory.forms import CounterpartyForm
from inventory.models import Counterparty, Sale




@test_mode_login_required
def counterparty_create(request):
    next_name = request.GET.get("next", "products_catalog")
    selected_products = request.GET.getlist("products")
    return_url = request.GET.get("return_url")

    if request.method == "POST":
        form = CounterpartyForm(request.POST, counterparty_type="supplier")
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.type = "supplier"
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
            # ВЫТАСКИВАЕМ ОШИБКИ
            print("=== ОШИБКИ ФОРМЫ ===", form.errors)
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Ошибка [{field}]: {error}")
    else:
        form = CounterpartyForm(counterparty_type="supplier")

    return render(request, "inventory/counterparty_form.html", {"form": form})


@test_mode_login_required
def customer_create(request):
    next_name = request.GET.get(
        "next",
        "sale_create"
    )
    selected_products = request.GET.getlist("products")
    if request.method == "POST":
        form = CounterpartyForm(request.POST, counterparty_type="customer")
        if form.is_valid():
            customer = form.save(commit=False)
            customer.type = "customer"
            try:
                customer.save()
                messages.success(request, f"Клиент «{customer.first_name} {customer.last_name}» создан.")
                # Собираем все нужные параметры в словарь/список
                query_kwargs = [('customer', customer.pk)]
                for product_id in selected_products:
                    query_kwargs.append(('products', product_id))

                # Формируем URL
                url = reverse(next_name)
                if query_kwargs:
                    # urlencode сам правильно склеит всё через & и закодирует спецсимволы
                    url += '?' + urlencode(query_kwargs)
                return redirect(url)
            except IntegrityError:
                messages.error(request, "Такой клиент уже существует.")
    else:
        form = CounterpartyForm(counterparty_type="customer")
    return render(request, "inventory/customer_form.html", {"form": form})


@test_mode_login_required
def customers_list(request):
    customers = (
        Counterparty.objects
        .filter(type='customer')
        .order_by('company_name', 'last_name', 'first_name')
    )
    return render(request, 'inventory/customers.html', {'customers': customers})


@test_mode_login_required
def customer_detail(request, pk):
    customer = get_object_or_404(Counterparty, pk=pk, type='customer')
    sales = Sale.objects.filter(customer=customer).annotate(
        calculated_total=Coalesce(
            Sum(F('items__quantity') * F('items__sale_price'), output_field=DecimalField()),
            Decimal('0.00')
        )
    ).order_by('-date', '-id')

    total_sales = sales.aggregate(
        total=Coalesce(Sum('calculated_total'), Decimal('0.00'))
    )['total']

    sales_count = sales.count()

    return render(request,'inventory/customer_detail.html', {
            'customer': customer,
            'sales': sales,
            'sales_count': sales_count,
            'total_sales': total_sales,
    })


@require_POST
def api_counterparty_create(request):
    c_type = request.POST.get('type')

    # Сохраняем поставщика
    if c_type == 'supplier':
        company_name = request.POST.get('company_name')
        inn = request.POST.get('inn', '')
        obj = Counterparty.objects.create(type='supplier', company_name=company_name, inn=inn)
        return JsonResponse({'id': obj.id, 'name': obj.company_name})

    # Сохраняем клиента
    elif c_type == 'customer':
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        obj = Counterparty.objects.create(type='customer', first_name=first_name, last_name=last_name)
        return JsonResponse({'id': obj.id, 'name': f"{last_name} {first_name}".strip()})

    return JsonResponse({'error': 'Неверный тип'}, status=400)