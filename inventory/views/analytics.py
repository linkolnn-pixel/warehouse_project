from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from inventory.models import Customer, Product, Receipt, Sale, Transaction, Warehouse


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

    # --- 2. ВЫРУЧКА, ПРИБЫЛЬ, ТОП ТОВАРОВ И ЛОГИСТИКА ЗА ПЕРИОДЫ ---
    now = timezone.now()

    def get_stats_since(days):
        start_date = now - timedelta(days=days)
        base_query = Sale.objects.filter(posted=True, date__gte=start_date)

        revenue_agg = base_query.aggregate(
            total=Sum(F("items__quantity") * F("items__sale_price"), output_field=DecimalField())
        )
        gross_revenue = float(revenue_agg["total"] or 0)

        profit_agg = base_query.aggregate(
            total=Sum(
                F("items__sale_price") * F("items__quantity")
                - Coalesce(F("items__fifo_cost"), F("items__cost_price") * F("items__quantity")),
                output_field=DecimalField(),
            )
        )
        gross_profit = float(profit_agg["total"] or 0)

        top_products = (
            base_query.values(product_name=F("items__product__name"))
            .annotate(total_sold=Sum("items__quantity"))
            .exclude(product_name__isnull=True)
            .exclude(product_name__icontains="Пакет")
            .order_by("-total_sold")[:3]
        )

        del_out_agg = base_query.aggregate(total=Sum("delivery_expense"))
        del_in_agg = Receipt.objects.filter(posted=True, date__gte=start_date).aggregate(total=Sum("delivery_cost"))

        delivery_out = float(del_out_agg["total"] or 0)
        delivery_in = float(del_in_agg["total"] or 0)
        total_delivery = delivery_out + delivery_in

        revenue = gross_revenue - delivery_out
        net_profit = gross_profit - delivery_out

        return revenue, net_profit, list(top_products), delivery_in, delivery_out, total_delivery

    periods = []
    for days, label in ((30, "За 30 дней"), (180, "За полгода"), (365, "За год")):
        revenue, profit, top_products, *_ = get_stats_since(days)
        periods.append(
            {
                "label": label,
                "revenue": revenue,
                "profit": profit,
                "margin": profit / revenue * 100 if revenue > 0 else None,
                "top_products": top_products,
            }
        )

    recent_transactions = Transaction.objects.select_related(
        "product", "warehouse", "receipt__supplier", "sale__customer"
    ).order_by("-date")[:5]

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
        "recent_transactions": recent_transactions,
        "periods": periods,
        # Переменные для блока анализа клиентов
        "analysis_data": analysis_data,
        "all_clients": all_clients,
        "selected_client": int(client_id) if client_id and client_id.isdigit() else "",
        "start_date": start_date,
        "end_date": end_date,
        "sort_by": sort_by,
    }

    return render(request, "inventory/dashboard.html", context)
