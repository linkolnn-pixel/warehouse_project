from django.shortcuts import render
from django.utils.dateparse import parse_date

from inventory.models import Customer, Sale


def analysis_view(request):
    # 1. Получаем параметры фильтров из GET-запроса
    client_id = request.GET.get("client_id")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    sort_by = request.GET.get("sort_by", "profit_desc")

    # Базовый запрос: все проведенные продажи с клиентами
    sales_qs = (
        Sale.objects.filter(posted=True, customer__isnull=False)
        .select_related("customer")
        .prefetch_related("items__product")
    )

    # 2. Фильтруем по датам
    if start_date:
        sales_qs = sales_qs.filter(date__date__gte=parse_date(start_date))
    if end_date:
        sales_qs = sales_qs.filter(date__date__lte=parse_date(end_date))

    # 3. Фильтруем по клиенту
    if client_id:
        sales_qs = sales_qs.filter(customer_id=client_id)

    # 4. Собираем данные
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

    # 5. Применяем сортировку (УБРАЛИ company_name, сортируем по фамилии и имени)
    if sort_by == "profit_desc":
        analysis_data.sort(key=lambda x: x["total_profit"], reverse=True)
    elif sort_by == "revenue_desc":
        analysis_data.sort(key=lambda x: x["total_revenue"], reverse=True)
    elif sort_by == "count_desc":
        analysis_data.sort(key=lambda x: x["sales_count"], reverse=True)
    elif sort_by == "name_asc":
        # Сортировка по фамилии по алфавиту
        analysis_data.sort(key=lambda x: (x["customer"].last_name or "").lower())

    # ОПТИМИЗАЦИЯ: Получаем уникальных клиентов, у которых есть проведенные продажи, одним легким SQL-запросом
    all_clients = Customer.objects.filter(sale__posted=True).distinct().order_by("last_name", "first_name")

    context = {
        "analysis_data": analysis_data,
        "all_clients": all_clients,
        # Передаем параметры обратно в шаблон, чтобы форма запоминала выбор
        "selected_client": int(client_id) if client_id and client_id.isdigit() else "",
        "start_date": start_date,
        "end_date": end_date,
        "sort_by": sort_by,
    }
    return render(request, "inventory/analysis.html", context)
