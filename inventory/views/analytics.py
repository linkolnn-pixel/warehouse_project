from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from inventory.models import Customer, Product, Sale, SaleItem, Warehouse


def _sales_periods(now):
    today = timezone.localdate(now)
    first_day = today - timedelta(days=364)
    start = timezone.make_aware(datetime.combine(first_day, time.min))
    sales = Sale.objects.filter(posted=True, date__range=(start, now)).order_by()
    items = SaleItem.objects.filter(sale__in=sales).order_by()
    revenue = F("quantity") * F("sale_price")
    profit = revenue - Coalesce(F("fifo_cost"), F("cost_price") * F("quantity"))
    daily_items = {
        row["day"]: (row["revenue"], row["profit"])
        for row in items.annotate(day=TruncDate("sale__date"))
        .values("day")
        .annotate(revenue=Sum(revenue, output_field=DecimalField()), profit=Sum(profit, output_field=DecimalField()))
    }
    daily_delivery = dict(
        sales.annotate(day=TruncDate("date"))
        .values("day")
        .annotate(delivery=Sum("delivery_expense"))
        .values_list("day", "delivery")
    )

    periods = []
    for key, days, label in (("month", 30, "30 дней"), ("half-year", 180, "Полгода"), ("year", 365, "Год")):
        first = today - timedelta(days=days - 1)
        buckets = {}
        for offset in range(days):
            day = first + timedelta(days=offset)
            bucket_start = first + timedelta(days=offset // 7 * 7) if days == 30 else day.replace(day=1)
            bucket = buckets.setdefault(
                bucket_start, {"start": day, "end": day, "revenue": 0, "profit": 0, "has_sales": False}
            )
            line_revenue, line_profit = daily_items.get(day, (0, 0))
            delivery = daily_delivery.get(day, 0)
            bucket["end"] = day
            bucket["revenue"] += line_revenue - delivery
            bucket["profit"] += line_profit - delivery
            bucket["has_sales"] |= day in daily_items or day in daily_delivery

        points = list(buckets.values())
        values = [point[metric] for point in points for metric in ("revenue", "profit")]
        lower, upper = min(0, min(values)), max(0, max(values))
        scale = upper - lower or 1
        for point in points:
            for metric in ("revenue", "profit"):
                value = point[metric]
                point[f"{metric}_bottom"] = (min(0, value) - lower) / scale * 100
                point[f"{metric}_height"] = abs(value) / scale * 100
            point["margin"] = point["profit"] / point["revenue"] * 100 if point["revenue"] > 0 else None

        period_items = (
            items.filter(sale__date__gte=timezone.make_aware(datetime.combine(first, time.min)))
            .exclude(product__name__icontains="Пакет")
            .values("product_id", "product__name")
            .annotate(units=Sum("quantity"), profit=Sum(profit, output_field=DecimalField()))
        )
        rankings = []
        for metric in ("units", "profit"):
            ranked = list(period_items.order_by(f"-{metric}", "product__name", "product_id")[:4])
            peak = max(ranked[0][metric], 0) if ranked else 0
            for row in ranked:
                row["value"] = row[metric]
                row["bar_width"] = max(row["value"], 0) / peak * 100 if peak else 0
            rankings.append({"metric": metric, "products": ranked})

        periods.append(
            {
                "key": key,
                "label": label,
                "points": points,
                "has_sales": any(point["has_sales"] for point in points),
                "zero_line": -lower / scale * 100,
                "rankings": rankings,
            }
        )
    return periods


@login_required
def dashboard_view(request):
    # --- 1. КАРТОЧКИ: Считаем текущие остатки ---
    warehouse = Warehouse.objects.first()
    warehouse_id = warehouse.id if warehouse else None
    products = Product.objects.with_balances(warehouse_id)

    total_stock_cost = sum(p.stock_cost for p in products)
    total_units = sum(max(p.balance or 0, 0) for p in products if p.name.strip().casefold() != "пакет")
    total_expected_profit = sum((p.stock_profit or 0) for p in products)
    out_of_stock_products = [p for p in products if (p.balance or 0) <= 0]
    out_of_stock_count = len(out_of_stock_products)

    product_count = len(products)
    low_stock_count = sum(0 < (p.balance or 0) <= 3 for p in products)
    stock_distribution = [
        {"status": status, "label": label, "percent": count / product_count * 100}
        for status, label, count in (
            ("available", "В наличии", product_count - low_stock_count - out_of_stock_count),
            ("low", "Мало (до 3 шт.)", low_stock_count),
            ("empty", "Закончился", out_of_stock_count),
        )
        if product_count
    ]

    # --- 4. АНАЛИЗ ПО КЛИЕНТАМ ---
    client_id = request.GET.get("client_id")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    sort_by = request.GET.get("sort_by", "profit_desc")

    sales_qs = (
        Sale.objects.filter(posted=True, customer__isnull=False)
        .select_related("customer")
        .prefetch_related("items__product")
        .order_by("-date", "-pk")
    )

    if start_date:
        sales_qs = sales_qs.filter(date__date__gte=parse_date(start_date))
    if end_date:
        sales_qs = sales_qs.filter(date__date__lte=parse_date(end_date))
    if client_id:
        sales_qs = sales_qs.filter(customer_id=client_id)

    clients_data = {}
    for sale in sales_qs:
        cid = sale.customer.id
        if cid not in clients_data:
            clients_data[cid] = {
                "customer": sale.customer,
                "latest_date": sale.date,
                "sales_count": 0,
                "total_revenue": 0,
                "total_profit": 0,
                "sales_list": [],
            }

        clients_data[cid]["sales_count"] += 1
        clients_data[cid]["total_revenue"] += sale.calculated_total or 0
        clients_data[cid]["total_profit"] += sale.net_profit or 0
        clients_data[cid]["sales_list"].append(sale)

    analysis_data = list(clients_data.values())
    for data in analysis_data:
        revenue = data["total_revenue"]
        data["margin"] = data["total_profit"] / revenue * 100 if revenue > 0 else None

    if sort_by == "profit_desc":
        analysis_data.sort(key=lambda x: x["total_profit"], reverse=True)
    elif sort_by == "revenue_desc":
        analysis_data.sort(key=lambda x: x["total_revenue"], reverse=True)
    elif sort_by == "count_desc":
        analysis_data.sort(key=lambda x: x["sales_count"], reverse=True)
    elif sort_by == "name_asc":
        analysis_data.sort(key=lambda x: (x["customer"].last_name or "").lower())

    all_clients = Customer.objects.filter(sale__posted=True).distinct().order_by("last_name", "first_name")

    context = {
        "total_stock_cost": total_stock_cost,
        "total_units": total_units,
        "total_expected_profit": total_expected_profit,
        "out_of_stock_count": out_of_stock_count,
        "out_of_stock_products": out_of_stock_products,
        "product_count": product_count,
        "stock_distribution": stock_distribution,
        "periods": _sales_periods(timezone.now()),
        # Переменные для блока анализа клиентов
        "analysis_data": analysis_data,
        "all_clients": all_clients,
        "selected_client": int(client_id) if client_id and client_id.isdigit() else "",
        "start_date": start_date,
        "end_date": end_date,
        "sort_by": sort_by,
    }

    return render(request, "inventory/dashboard.html", context)
