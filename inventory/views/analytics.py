import json
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import TruncDate
from django.shortcuts import render

from inventory.models import Product, Sale, Transaction


def dashboard_view(request):
    # --- 1. КАРТОЧКИ: Считаем текущие остатки ---
    products = Product.objects.with_balances()

    total_stock_cost = sum((p.balance or 0) * p.cost_price for p in products)
    total_expected_profit = sum((p.stock_profit or 0) for p in products)
    out_of_stock_count = sum(1 for p in products if (p.balance or 0) <= 0)

    # --- 2. ГРАФИК: Выручка за последние 7 дней ---
    today = timezone.now().date()
    # Генерируем список дат от (сегодня - 6 дней) до сегодня
    last_7_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]

    # Подготавливаем словари для графика (по умолчанию везде нули)
    # Форматируем даты как 'ДД.ММ', например '24.09'
    labels = [day.strftime('%d.%m') for day in last_7_days]
    revenue_by_date = {day: 0 for day in last_7_days}

    # Делаем ОДИН запрос к БД:
    # Берем проведенные продажи за последние 7 дней, группируем по дате
    # и считаем сумму: количество * цена_продажи
    sales_data = (
        Sale.objects.filter(posted=True, date__date__gte=last_7_days[0])
        .annotate(day=TruncDate('date'))
        .values('day')
        .annotate(
            total_revenue=Sum(
                F('items__quantity') * F('items__sale_price'),
                output_field=DecimalField()
            )
        )
    )

    # Заполняем наш словарь реальными данными из БД
    for item in sales_data:
        day = item['day']
        if day in revenue_by_date:
            revenue_by_date[day] = float(item['total_revenue'] or 0)

    # Превращаем словарь в список значений, чтобы отдать в график
    data_values = [revenue_by_date[day] for day in last_7_days]

    # --- 3. ПОСЛЕДНИЕ СОБЫТИЯ ---
    recent_transactions = Transaction.objects.select_related(
        'product', 'warehouse'
    ).order_by('-date')[:5]

    context = {
        'total_stock_cost': total_stock_cost,
        'total_expected_profit': total_expected_profit,
        'out_of_stock_count': out_of_stock_count,
        'recent_transactions': recent_transactions,

        # Передаем данные для графика в формате JSON (чтобы JS их понял)
        'chart_labels': json.dumps(labels),
        'chart_data': json.dumps(data_values),
    }

    return render(request, 'inventory/dashboard.html', context)