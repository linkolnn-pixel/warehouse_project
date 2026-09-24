from collections import OrderedDict

from django.shortcuts import render

from inventory.decorators import test_mode_login_required
from inventory.models import Category, Product, Transaction, Warehouse


@test_mode_login_required
def stock_management_view(request):
    warehouse = Warehouse.objects.first()  # Берем первый склад для отображения
    categories = Category.objects.all()

    warehouse_id = warehouse.id if warehouse else None
    products = Product.objects.with_balances(warehouse_id).select_related("category")

    total_quantity = 0
    total_cost = 0
    total_retail = 0

    for p in products:
        balance = p.balance or 0
        if balance > 0:
            total_quantity += balance
            total_cost += balance * p.cost_price
            total_retail += balance * p.sale_price

    total_profit = total_retail - total_cost

    return render(
        request,
        "inventory/stock_page.html",
        {
            "page_title": "Управление остатками",
            "products": products,
            "warehouse": warehouse,
            "categories": categories,
            "total_quantity": total_quantity,
            "total_cost": total_cost,
            "total_retail": total_retail,
            "total_profit": total_profit,
        },
    )


@test_mode_login_required
def movement_report(request):
    transactions = Transaction.objects.select_related(
        "product",
        "warehouse",
        "counterparty",
        "receipt",
        "sale",
    ).order_by("-date", "-id")

    grouped_docs = OrderedDict()

    for tx in transactions:
        # 1. Определяем, к какому документу относится транзакция
        if tx.receipt_id:
            doc_key = f"receipt_{tx.receipt_id}"
            doc_type = "IN"
            doc_obj = tx.receipt
            counterparty = tx.receipt.supplier
            url_name = "receipt_detail"
            doc_number = tx.receipt.number
            reference = tx.receipt.comment  # Берем комментарий из прихода
        elif tx.sale_id:
            doc_key = f"sale_{tx.sale_id}"
            doc_type = "OUT"
            doc_obj = tx.sale
            counterparty = tx.sale.customer
            url_name = "sale_detail"
            doc_number = tx.sale.number
            reference = tx.sale.comment  # Берем комментарий из продажи
        else:
            # Если это какая-то ручная транзакция без документа
            doc_key = f"manual_{tx.id}"
            doc_type = tx.type
            doc_obj = None
            counterparty = tx.counterparty
            url_name = None
            doc_number = None
            reference = ""  # Ручная транзакция без комментария

        # 2. Если такого документа еще нет в нашем словаре — добавляем
        if doc_key not in grouped_docs:
            grouped_docs[doc_key] = {
                "key": doc_key,
                "date": tx.date,
                "type": doc_type,
                "warehouse": tx.warehouse,
                "counterparty": counterparty,
                "document": doc_obj,
                "url_name": url_name,
                "doc_number": doc_number,
                "items_dict": {},
                "reference": reference,  # Передаем найденный комментарий
            }

        # 3. Добавляем товар в документ и суммируем количество, если он повторяется
        doc_data = grouped_docs[doc_key]
        if tx.product:
            prod_id = tx.product.id
            if prod_id not in doc_data["items_dict"]:
                doc_data["items_dict"][prod_id] = {"product": tx.product, "quantity": 0}
            doc_data["items_dict"][prod_id]["quantity"] += tx.quantity

        # 4. Преобразуем словарь товаров обратно в список для удобства в шаблоне
    documents = []
    for doc in grouped_docs.values():
        doc["items"] = list(doc["items_dict"].values())
        documents.append(doc)

    return render(request, "inventory/movement_report.html", {"documents": documents})
