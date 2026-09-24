from django.db import models
from django.db.models import Sum, Q, F, Value, IntegerField, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce

class ProductManager(models.Manager):
    def with_balances(self, warehouse_id=None):
        """
        Возвращает QuerySet товаров, к каждому из которых добавлены поля:
        - balance (остаток на указанном складе)
        - profit (прибыль с одной единицы)
        - stock_profit (общая прибыль остатков на складе)
        """
        qs = self.get_queryset()

        if not warehouse_id:
            # Если склад не передан, возвращаем товары с нулевыми остатками
            return qs.annotate(
                balance=Value(0, output_field=IntegerField()),
                profit=F('sale_price') - F('cost_price'),
                stock_profit=Value(0.00, output_field=DecimalField())
            )

        # Условия фильтрации транзакций по конкретному складу и типу
        in_q = Q(transactions__warehouse_id=warehouse_id, transactions__type='IN')
        out_q = Q(transactions__warehouse_id=warehouse_id, transactions__type='OUT')

        qs = qs.annotate(
            # Считаем сумму приходов
            in_qty=Coalesce(
                Sum('transactions__quantity', filter=in_q),
                Value(0),
                output_field=IntegerField()
            ),
            # Считаем сумму расходов
            out_qty=Coalesce(
                Sum('transactions__quantity', filter=out_q),
                Value(0),
                output_field=IntegerField()
            ),
            # Баланс = Приход - Расход
            balance=F('in_qty') - F('out_qty'),
            # Прибыль = Цена продажи - Закупочная цена
            profit=F('sale_price') - F('cost_price')
        )

        qs = qs.annotate(
            stock_profit=ExpressionWrapper(
                F('balance') * F('profit'),
                output_field=DecimalField()
            )
        )

        return qs