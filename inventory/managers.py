from django.db import models
from django.db.models import (
    DecimalField,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce


class ActiveManager(models.Manager):
    """Возвращает только не удаленные записи."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class ProductManager(ActiveManager):
    def with_balances(self, warehouse_id=None):
        """
        Возвращает QuerySet товаров, к каждому из которых добавлены поля:
        - balance (остаток на указанном складе)
        - profit_per_unit (прибыль с одной единицы)
        - stock_profit (общая прибыль остатков на складе)
        """
        from .models import StockLot

        qs = self.get_queryset()

        if not warehouse_id:
            # Если склад не передан, возвращаем товары с нулевыми остатками
            return qs.annotate(
                balance=Value(0, output_field=IntegerField()),
                profit=F("sale_price") - F("cost_price"),
                stock_cost=Value(0, output_field=DecimalField()),
                stock_profit=Value(0.00, output_field=DecimalField()),
            )

        # Условия фильтрации транзакций по конкретному складу и типу
        in_q = Q(transactions__warehouse_id=warehouse_id, transactions__type="IN")
        out_q = Q(transactions__warehouse_id=warehouse_id, transactions__type="OUT")
        lots = (
            StockLot.objects.filter(balance__product_id=OuterRef("pk"), balance__warehouse_id=warehouse_id)
            .values("balance_id")
            .annotate(cost=Sum("remaining_cost"))
            .values("cost")
        )

        return qs.annotate(
            # Считаем сумму приходов
            in_qty=Coalesce(
                Sum("transactions__quantity", filter=in_q),
                Value(0),
                output_field=IntegerField(),
            ),
            # Считаем сумму расходов
            out_qty=Coalesce(
                Sum("transactions__quantity", filter=out_q),
                Value(0),
                output_field=IntegerField(),
            ),
            # Баланс = Приход - Расход
            balance=F("in_qty") - F("out_qty"),
            # Прибыль = Цена продажи - Закупочная цена
            profit_per_unit=F("sale_price") - F("cost_price"),
            stock_cost=Coalesce(Subquery(lots), Value(0), output_field=DecimalField()),
        ).annotate(
            stock_profit=F("balance") * F("sale_price") - F("stock_cost"),
        )
