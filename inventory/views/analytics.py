from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, F, Sum
from django.shortcuts import render
from django.utils import timezone

# ВАЖНО: Добавлена модель Receipt в импорт
from inventory.models import Product, Receipt, Sale, SaleItem, Transaction, Warehouse


def dashboard_view(request):
    # --- 1. КАРТОЧКИ: Считаем текущие остатки ---
    warehouse = Warehouse.objects.first()
    warehouse_id = warehouse.id if warehouse else None
    products = Product.objects.with_balances(warehouse_id)

    total_stock_cost = sum((p.balance or 0) * p.cost_price for p in products)
    total_expected_profit = sum((p.stock_profit or 0) for p in products)
    out_of_stock_products = [p for p in products if (p.balance or 0) <= 0]
    out_of_stock_count = len(out_of_stock_products)

    # --- 2. ВЫРУЧКА, ПРИБЫЛЬ, ТОП ТОВАРОВ И ЛОГИСТИКА ЗА ПЕРИОДЫ ---
    now = timezone.now()

    def get_stats_since(days):
        start_date = now - timedelta(days=days)
        base_query = Sale.objects.filter(posted=True, date__gte=start_date)

        # 2.1 Считаем общую выручку за период
        revenue_agg = base_query.aggregate(
            total=Sum(
                F("items__quantity") * F("items__sale_price"),
                output_field=DecimalField(),
            )
        )
        gross_revenue = float(revenue_agg["total"] or 0)

        # 2.2 Считаем маржу (выручка минус себестоимость проданных товаров)
        profit_agg = base_query.aggregate(
            total=Sum(
                (F("items__sale_price") - F("items__cost_price")) * F("items__quantity"),
                output_field=DecimalField(),
            )
        )
        gross_profit = float(profit_agg["total"] or 0)

        # 2.3 Определяем топ-3 товара
        top_products = (
            base_query.values(product_name=F("items__product__name"))
            .annotate(total_sold=Sum("items__quantity"))
            .exclude(product_name__isnull=True)
            .order_by("-total_sold")[:3]
        )

        # 2.4 Считаем логистику
        del_out_agg = base_query.aggregate(total=Sum("delivery_expense"))
        del_in_agg = Receipt.objects.filter(posted=True, date__gte=start_date).aggregate(total=Sum("delivery_cost"))

        delivery_out = float(del_out_agg["total"] or 0)
        delivery_in = float(del_in_agg["total"] or 0)
        total_delivery = delivery_out + delivery_in

        # ВЫЧИТАЕМ доставку из выручки и маржи!
        revenue = gross_revenue - delivery_out
        net_profit = gross_profit - delivery_out

        return revenue, net_profit, list(top_products), delivery_in, delivery_out, total_delivery

    # Получаем данные за 30, 180 и 365 дней
    revenue_1m, profit_1m, top_1m, delivery_in_1m, delivery_out_1m, total_delivery_1m = get_stats_since(30)
    revenue_6m, profit_6m, top_6m, delivery_in_6m, delivery_out_6m, total_delivery_6m = get_stats_since(180)
    revenue_1y, profit_1y, top_1y, delivery_in_1y, delivery_out_1y, total_delivery_1y = get_stats_since(365)

    # --- 3. ПОСЛЕДНИЕ СОБЫТИЯ ---
    recent_transactions = Transaction.objects.select_related("product", "warehouse").order_by("-date")[:5]

    context = {
        "total_stock_cost": total_stock_cost,
        "total_expected_profit": total_expected_profit,
        "out_of_stock_count": out_of_stock_count,
        "out_of_stock_products": out_of_stock_products,
        "recent_transactions": recent_transactions,
        "revenue_1m": revenue_1m,
        "profit_1m": profit_1m,
        "revenue_6m": revenue_6m,
        "profit_6m": profit_6m,
        "revenue_1y": revenue_1y,
        "profit_1y": profit_1y,
        "top_1m": top_1m,
        "top_6m": top_6m,
        "top_1y": top_1y,
        "delivery_in_1m": delivery_in_1m,
        "delivery_out_1m": delivery_out_1m,
        "total_delivery_1m": total_delivery_1m,
        "delivery_in_6m": delivery_in_6m,
        "delivery_out_6m": delivery_out_6m,
        "total_delivery_6m": total_delivery_6m,
        "delivery_in_1y": delivery_in_1y,
        "delivery_out_1y": delivery_out_1y,
        "total_delivery_1y": total_delivery_1y,
    }

    return render(request, "inventory/dashboard.html", context)


def abc_analysis_view(request):
    """
    Рассчитывает ABC-анализ на основе выручки по проведенным продажам.
    """
    # 1. Получаем выручку по каждому товару (только проведенные продажи)
    sales_data = (
        SaleItem.objects.filter(sale__posted=True)
        .values("product__id", "product__name", "product__sku")
        .annotate(total_revenue=Sum(F("quantity") * F("sale_price"), output_field=DecimalField()))
        .order_by("-total_revenue")
    )

    # 2. Считаем общую выручку по всем товарам
    total_revenue_all = sum((item["total_revenue"] or 0) for item in sales_data)

    abc_data = []
    if total_revenue_all > 0:
        cumulative_revenue = Decimal("0.0")

        # 3. Распределяем товары по классам (80% / 15% / 5%)
        for item in sales_data:
            revenue = item["total_revenue"] or Decimal("0.0")
            if revenue <= 0:
                continue

            cumulative_revenue += revenue
            cumulative_percentage = (cumulative_revenue / total_revenue_all) * 100

            if cumulative_percentage <= 80:
                abc_class = "A"
            elif cumulative_percentage <= 95:
                abc_class = "B"
            else:
                abc_class = "C"

            abc_data.append(
                {
                    "id": item["product__id"],
                    "name": item["product__name"],
                    "sku": item["product__sku"],
                    "revenue": revenue,
                    "share": (revenue / total_revenue_all) * 100,
                    "abc_class": abc_class,
                }
            )

    context = {
        "abc_data": abc_data,
        "total_revenue": total_revenue_all,
    }
    return render(request, "inventory/abc_analysis.html", context)
