from django.db import transaction

from inventory.models import SaleItem

items_to_fix = SaleItem.objects.filter(cost_price=0)
fixed_count = 0

with transaction.atomic():
    for item in items_to_fix:
        correct_cost = item.product.average_cost if item.product.average_cost > 0 else item.product.cost_price

        if correct_cost > 0:
            item.cost_price = correct_cost
            item.save(update_fields=["cost_price"])
            fixed_count += 1

print(f"Успешно исправлено позиций в старых продажах: {fixed_count}")
