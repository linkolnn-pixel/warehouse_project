from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

from inventory.models import SaleItem


def client_predictions_view(request):
    # Берем проведенные продажи с клиентами, где у товара указан срок расхода > 0
    sale_items = SaleItem.objects.select_related("sale", "sale__customer", "product").filter(
        sale__posted=True, sale__customer__isnull=False, product__consumption_time__gt=0
    )

    predictions = []
    now = timezone.now()

    for item in sale_items:
        # Переводим месяцы в дни (приближенно 1 месяц = 30 дней)
        days_to_consume = int(float(item.product.consumption_time) * 30)
        # Дата, когда товар закончится
        exhaustion_date = item.sale.date + timedelta(days=days_to_consume)

        # Сколько дней осталось до конца
        days_left = (exhaustion_date - now).days

        predictions.append(
            {
                "customer": item.sale.customer,
                "product": item.product,
                "purchase_date": item.sale.date,
                "exhaustion_date": exhaustion_date,
                "days_left": days_left,
            }
        )

    # Сортируем: сначала те, у кого товар заканчивается прямо сейчас или уже закончился
    predictions.sort(key=lambda x: x["exhaustion_date"])
    brands = set(item.product.brand for item in sale_items if item.product.brand)

    return render(
        request,
        "inventory/client_predictions.html",
        {
            "predictions": predictions,
            "brands": sorted(brands),
        },
    )
