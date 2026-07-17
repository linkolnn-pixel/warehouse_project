from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Q
from datetime import datetime, timedelta
from .models import Product, Warehouse, Transaction, Counterparty
from .forms import InboundForm, OutboundForm

def dashboard(request):
    # Сводный отчёт: остатки по всем товарам и складам
    warehouses = Warehouse.objects.all()
    products = Product.objects.all()

    rows = []
    for product in products:
        row = {'product': product}
        for wh in warehouses:
            balance = product.get_balance(wh)
            row[wh.id] = balance
        rows.append(row)

    return render(request, 'inventory/dashboard.html', {
        'rows': rows,
        'warehouses': warehouses,
    })

def inbound_view(request):
    if request.method == 'POST':
        form = InboundForm(request.POST)
        if form.is_valid():
            tx = form.save(commit=False)
            tx.type = 'IN'
            tx.save()
            messages.success(request, "Товар успешно оприходован.")
            return redirect('dashboard')
    else:
        form = InboundForm()
    return render(request, 'inventory/inbound.html', {'form': form, 'title': 'Оприходование'})

def outbound_view(request):
    if request.method == 'POST':
        form = OutboundForm(request.POST)
        if form.is_valid():
            try:
                tx = form.save(commit=False)
                tx.type = 'OUT'
                tx.save()
                messages.success(request, "Отгрузка оформлена.")
                return redirect('dashboard')
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = OutboundForm()
    return render(request, 'inventory/outbound.html', {'form': form, 'title': 'Отгрузка'})

def movement_report(request):
    qs = Transaction.objects.select_related('product', 'warehouse', 'counterparty').all()

    # Фильтры
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    product_id = request.GET.get('product')
    warehouse_id = request.GET.get('warehouse')

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    if product_id:
        qs = qs.filter(product_id=product_id)
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    # Итого по типам
    totals = qs.values('type').annotate(total_qty=Sum('quantity'))

    products = Product.objects.all()
    warehouses = Warehouse.objects.all()

    return render(request, 'inventory/movement_report.html', {
        'transactions': qs,
        'totals': totals,
        'products': products,
        'warehouses': warehouses,
        'filters': request.GET,
    })
