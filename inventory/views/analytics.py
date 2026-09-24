from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, F, DecimalField
from django.shortcuts import render

from inventory.models import Product, Sale, Transaction, Warehouse


def dashboard_view(request):
    # --- 1. КАРТОЧКИ: Считаем текущие остатки ---
    warehouse = Warehouse.objects.first()
    warehouse_id = warehouse.id if warehouse else None
    products = Product.objects.with_balances(warehouse_id)

    total_stock_cost = sum((p.balance or 0) * p.cost_price for p in products)
    total_expected_profit = sum((p.stock_profit or 0) for p in products)
    out_of_stock_products = [p for p in products if (p.balance or 0) <= 0]
    out_of_stock_count = len(out_of_stock_products)

    # --- 2. ВЫРУЧКА И ТОП ТОВАРОВ ЗА ПЕРИОДЫ ---
    now = timezone.now()

    def get_stats_since(days):
        start_date = now - timedelta(days=days)

        # 2.1 Считаем общую выручку за период
        revenue_agg = Sale.objects.filter(
            posted=True,
            date__gte=start_date
        ).aggregate(
            total=Sum(
                F('items__quantity') * F('items__sale_price'),
                output_field=DecimalField()
            )
        )
        revenue = float(revenue_agg['total'] or 0)

        # 2.2 Определяем топ-3 товара по количеству проданных единиц
        top_products = Sale.objects.filter(
            posted=True,
            date__gte=start_date
        ).values(
            product_name=F('items__product__name')
        ).annotate(
            total_sold=Sum('items__quantity')
        ).exclude(
            product_name__isnull=True
        ).order_by('-total_sold')[:3]

        return revenue, list(top_products)

    # Получаем данные за 30, 180 и 365 дней
    revenue_1m, top_1m = get_stats_since(30)
    revenue_6m, top_6m = get_stats_since(180)
    revenue_1y, top_1y = get_stats_since(365)

    # --- 3. ПОСЛЕДНИЕ СОБЫТИЯ ---
    recent_transactions = Transaction.objects.select_related(
        'product', 'warehouse'
    ).order_by('-date')[:5]

    context = {
        'total_stock_cost': total_stock_cost,
        'total_expected_profit': total_expected_profit,
        'out_of_stock_count': out_of_stock_count,
        'out_of_stock_products': out_of_stock_products,
        'recent_transactions': recent_transactions,

        'revenue_1m': revenue_1m,
        'revenue_6m': revenue_6m,
        'revenue_1y': revenue_1y,

        'top_1m': top_1m,
        'top_6m': top_6m,
        'top_1y': top_1y,
    }

    return render(request, 'inventory/dashboard.html', context)