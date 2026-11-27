from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pandas as pd
from django.db import transaction
from django.db.models import Case, F, Value, When

from .exceptions import (
    DocumentAlreadyPostedError,
    ExcelImportError,
    InsufficientStockError,
    InvalidQuantityError,
)
from .models import (
    Category,
    Product,
    PromoCode,
    Receipt,
    Sale,
    SaleItem,
    StockAllocation,
    StockBalance,
    StockLot,
    Supplier,
    Transaction,
)


@transaction.atomic
def import_products_from_excel(file_obj) -> tuple[int, int]:
    """
    Импорт товаров из Excel.
    Возвращает: (количество_созданных, количество_пропущенных)
    Если во время импорта произойдет исключение, вся транзакция
    будет откатана.
    """
    try:
        df = pd.read_excel(file_obj)
    except Exception as e:
        raise ExcelImportError(f"Не удалось прочитать файл Excel: {e}") from e

    # Нормализация заголовков
    df.columns = df.columns.str.strip().str.lower()

    required_cols = [
        "наименование",
        "закупочная цена",
        "цена продажи",
    ]

    missing = [col for col in required_cols if col not in df.columns]

    if missing:
        raise ExcelImportError(f"В файле не найдены колонки: {', '.join(missing)}")

    # Кэши существующих сущностей
    categories_cache = {category.name: category for category in Category.objects.all()}

    suppliers_cache = {supplier.company_name: supplier for supplier in Supplier.objects.all()}

    existing_skus = set(Product.objects.exclude(sku="").values_list("sku", flat=True))

    existing_names = set(Product.objects.values_list("name", flat=True))

    products_to_create = []
    skip_count = 0

    for _, row in df.iterrows():
        # 1. Наименование
        name_raw = row.get("наименование")

        if pd.isna(name_raw):
            continue

        name = str(name_raw).strip()

        if not name or name.lower() == "nan":
            continue

        # 2. SKU
        sku_raw = row.get("артикул", "")

        sku = str(sku_raw).strip() if pd.notna(sku_raw) else ""

        # Проверяем дубли как в БД, так и внутри текущего Excel.
        if sku:
            if sku in existing_skus:
                skip_count += 1
                continue
        elif name in existing_names:
            skip_count += 1
            continue

        # 3. Цены
        try:
            cost_raw = row["закупочная цена"]
            sale_raw = row["цена продажи"]

            cost_str = str(cost_raw).replace(",", ".").strip()
            sale_str = str(sale_raw).replace(",", ".").strip()

            cost_price = Decimal(cost_str)
            sale_price = Decimal(sale_str)

            if cost_price < 0 or sale_price < 0:
                skip_count += 1
                continue

        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):
            skip_count += 1
            continue

        # 4. Вес / объем / единица измерения
        vol_raw = row.get("объем", 0)
        weight_raw = row.get("вес", 0)

        final_quantity = Decimal("0")
        final_measure = "мл"

        final_unit_raw = row.get("ед. изм.", "шт")

        if pd.notna(final_unit_raw):
            final_unit = str(final_unit_raw).strip().lower()
        else:
            final_unit = "шт"

        if pd.notna(vol_raw) and str(vol_raw).lower() != "nan":
            try:
                value = Decimal(str(vol_raw).replace(",", ".").strip())

                if value > 0:
                    final_quantity = value
                    final_measure = "мл"

            except (
                InvalidOperation,
                ValueError,
                TypeError,
            ):
                pass

        elif pd.notna(weight_raw) and str(weight_raw).lower() != "nan":
            try:
                value = Decimal(str(weight_raw).replace(",", ".").strip())

                if value > 0:
                    final_quantity = value
                    final_measure = "г"

            except (
                InvalidOperation,
                ValueError,
                TypeError,
            ):
                pass

        # 5. Категория / бренд
        brand_raw = row.get(
            "бренд",
            row.get("category_name", ""),
        )

        brand_name = str(brand_raw).strip() if pd.notna(brand_raw) else ""
        # 6. Поставщик
        supplier_raw = row.get(
            "поставщик",
            row.get("supplier", ""),
        )

        supplier_name = (
            str(supplier_raw).strip() if pd.notna(supplier_raw) and str(supplier_raw).lower() != "nan" else ""
        )
        # 7. Создаем / получаем категорию
        category_obj = None

        if brand_name:
            category_obj = categories_cache.get(brand_name)

            if category_obj is None:
                category_obj = Category.objects.create(
                    name=brand_name,
                    parent=None,
                )

                categories_cache[brand_name] = category_obj

        # 8. Создаем / получаем поставщика
        supplier_obj = None

        if supplier_name:
            supplier_obj = suppliers_cache.get(supplier_name)

            if supplier_obj is None:
                supplier_obj = Supplier.objects.create(company_name=supplier_name)

                suppliers_cache[supplier_name] = supplier_obj

        # 9. Формируем товар
        product = Product(
            name=name,
            category=category_obj,
            supplier=supplier_obj,
            sku=sku,
            unit=final_unit,
            cost_price=cost_price,
            sale_price=sale_price,
            quantity_value=final_quantity,
            measure_unit=final_measure,
        )

        products_to_create.append(product)

        # сразу добавляем новые значения в кэш,
        # чтобы дубли внутри одного Excel тоже отбрасывались.
        if sku:
            existing_skus.add(sku)

        existing_names.add(name)

    # 10. Массовое создание
    if products_to_create:
        Product.objects.bulk_create(products_to_create)

    return len(products_to_create), skip_count


def _money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _lock_products(items):
    ids = {item.product_id for item in items}
    products = Product.all_objects.select_for_update().filter(pk__in=ids).order_by("pk")
    return {product.pk: product for product in products}


def _get_balance(product_id, warehouse_id):
    balance, _ = StockBalance.objects.select_for_update().get_or_create(
        product_id=product_id, warehouse_id=warehouse_id
    )
    return balance


@transaction.atomic
def process_receipt_post(receipt: Receipt):
    receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.posted:
        raise DocumentAlreadyPostedError("Приход", receipt.number)

    items = list(receipt.items.select_related("product").order_by("pk"))
    for item in items:
        if item.quantity <= 0:
            raise InvalidQuantityError(item.product.name)

    products = _lock_products(items)
    total_goods = sum(item.total_cost for item in items)
    weights = [item.total_cost if total_goods else item.quantity for item in items]
    total_weight = sum(weights)
    cumulative_weight = 0
    allocated_delivery = Decimal("0")
    balances = {}
    lots = []
    movements = []

    for item, weight in zip(items, weights, strict=True):
        product = products[item.product_id]
        if product.pk not in balances:
            balances[product.pk] = _get_balance(product.pk, receipt.warehouse_id)
        balance = balances[product.pk]

        cumulative_weight += weight
        delivery_to_date = _money(receipt.delivery_cost * cumulative_weight / total_weight)
        lot_cost = item.total_cost + delivery_to_date - allocated_delivery
        allocated_delivery = delivery_to_date

        # A legacy negative balance absorbs part of the new receipt.
        sellable = max(Decimal("0"), min(Decimal(item.quantity), balance.quantity + item.quantity))
        lots.append(
            StockLot(
                balance=balance,
                receipt_item=item,
                remaining_quantity=sellable,
                remaining_cost=_money(lot_cost * sellable / item.quantity),
            )
        )
        balance.quantity += item.quantity
        product.cost_price = item.cost_price
        product.sale_price = item.sale_price
        movements.append(
            Transaction(
                date=receipt.date,
                type="IN",
                product=product,
                warehouse_id=receipt.warehouse_id,
                quantity=item.quantity,
                receipt=receipt,
                comment=f"Приход №{receipt.number}",
            )
        )

    StockBalance.objects.bulk_update(balances.values(), ["quantity"])
    StockLot.objects.bulk_create(lots)
    Transaction.objects.bulk_create(movements)
    Product.all_objects.bulk_update(products.values(), ["cost_price", "sale_price"])
    receipt.posted = True
    receipt.save(update_fields=["posted"])


@transaction.atomic
def process_receipt_unpost(receipt: Receipt):
    receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)
    if not receipt.posted:
        raise ValueError(f"Приход №{receipt.number} не проведён.")

    items = list(receipt.items.order_by("pk"))
    _lock_products(items)
    lots = {
        lot.receipt_item_id: lot for lot in StockLot.objects.select_for_update().filter(receipt_item__receipt=receipt)
    }
    balances = {}
    for item in items:
        lot = lots.get(item.pk)
        if lot is None:
            raise ValueError("Этот приход включён в начальный остаток FIFO. Отменить его проведение нельзя.")
        if lot.remaining_quantity != item.quantity:
            raise ValueError("Часть партии уже списана. Сначала отмените зависимые продажи.")
        if item.product_id not in balances:
            balances[item.product_id] = _get_balance(item.product_id, receipt.warehouse_id)
        balances[item.product_id].quantity -= item.quantity

    StockBalance.objects.bulk_update(balances.values(), ["quantity"])
    StockLot.objects.filter(pk__in=[lot.pk for lot in lots.values()]).delete()
    Transaction.objects.filter(receipt=receipt).delete()
    receipt.posted = False
    receipt.save(update_fields=["posted"])


def _allocate_fifo(item, lots):
    needed = Decimal(item.quantity)
    allocations = []
    for lot in lots:
        if not lot.remaining_quantity:
            continue
        quantity = min(needed, lot.remaining_quantity)
        cost = _money(lot.remaining_cost * quantity / lot.remaining_quantity)
        allocations.append(StockAllocation(sale_item=item, lot=lot, quantity=quantity, cost=cost))
        lot.remaining_quantity -= quantity
        lot.remaining_cost -= cost
        needed -= quantity
        if not needed:
            return allocations
    raise ValueError(f"Остаток товара «{item.product.name}» не совпадает с остатком партий FIFO.")


@transaction.atomic
def process_sale_post(sale: Sale):
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.posted:
        raise DocumentAlreadyPostedError("Продажа", sale.number)

    items = list(sale.items.select_related("product").order_by("pk"))
    quantities: dict[int, int] = {}
    for item in items:
        if item.quantity <= 0:
            raise InvalidQuantityError(item.product.name)
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    products = _lock_products(items)
    balances = {}
    lots_by_product = {}
    for product_id, quantity in quantities.items():
        balance = _get_balance(product_id, sale.warehouse_id)
        if quantity > balance.quantity:
            raise InsufficientStockError(products[product_id].name, balance.quantity, quantity)
        balances[product_id] = balance
        lots_by_product[product_id] = list(
            balance.lots.select_for_update()
            .filter(remaining_quantity__gt=0)
            .order_by(Case(When(receipt_item__isnull=True, then=Value(0)), default=Value(1)), "pk")
        )
        balance.quantity -= quantity

    allocations = []
    movements = []
    for item in items:
        consumed = _allocate_fifo(item, lots_by_product[item.product_id])
        item.fifo_cost = sum(allocation.cost for allocation in consumed)
        item.cost_price = _money(item.fifo_cost / item.quantity)
        allocations.extend(consumed)
        movements.append(
            Transaction(
                date=sale.date,
                type="OUT",
                product_id=item.product_id,
                warehouse_id=sale.warehouse_id,
                quantity=item.quantity,
                sale=sale,
                comment=f"Продажа №{sale.number}",
            )
        )

    StockBalance.objects.bulk_update(balances.values(), ["quantity"])
    StockLot.objects.bulk_update(
        {allocation.lot_id: allocation.lot for allocation in allocations}.values(),
        ["remaining_quantity", "remaining_cost"],
    )
    StockAllocation.objects.bulk_create(allocations)
    SaleItem.objects.bulk_update(items, ["cost_price", "fifo_cost"])
    Transaction.objects.bulk_create(movements)
    if sale.promo_code_id:
        PromoCode.objects.filter(pk=sale.promo_code_id).update(used_count=F("used_count") + 1)
    sale.posted = True
    sale.save(update_fields=["posted"])


@transaction.atomic
def process_sale_unpost(sale: Sale):
    """
    Отмена проведения продажи.
    Удаляет созданные этим документом OUT-транзакции
    и переводит документ обратно в состояние draft,
    возвращает остатки на склад и откатывает счетчик промокода.
    """
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if not sale.posted:
        raise ValueError(f"Продажа №{sale.number} не проведена.")

    items = list(sale.items.order_by("pk"))
    _lock_products(items)
    balances = {}
    opening_lots = []
    restored_lots: dict[int, StockLot] = {}
    allocations = StockAllocation.objects.filter(sale_item__sale=sale)
    allocations_by_item: dict[int, list[StockAllocation]] = {}
    for allocation in allocations.select_related("lot"):
        allocations_by_item.setdefault(allocation.sale_item_id, []).append(allocation)

    for item in items:
        if item.product_id not in balances:
            balances[item.product_id] = _get_balance(item.product_id, sale.warehouse_id)
        balance = balances[item.product_id]
        if item.fifo_cost is None:
            # Legacy sales have no traceable lot; use their stored unit cost.
            sellable = max(Decimal("0"), min(Decimal(item.quantity), balance.quantity + item.quantity))
            if sellable:
                opening_lots.append(
                    StockLot(
                        balance=balance,
                        remaining_quantity=sellable,
                        remaining_cost=_money(sellable * item.cost_price),
                    )
                )
        else:
            consumed = allocations_by_item.get(item.pk, [])
            if sum(allocation.quantity for allocation in consumed) != item.quantity:
                raise ValueError("Списания FIFO этой продажи не совпадают с количеством товаров.")
            for allocation in consumed:
                lot = restored_lots.setdefault(allocation.lot_id, allocation.lot)
                lot.remaining_quantity += allocation.quantity
                lot.remaining_cost += allocation.cost
        balance.quantity += item.quantity
        item.fifo_cost = None

    StockBalance.objects.bulk_update(balances.values(), ["quantity"])
    StockLot.objects.bulk_create(opening_lots)
    StockLot.objects.bulk_update(restored_lots.values(), ["remaining_quantity", "remaining_cost"])
    allocations.delete()
    SaleItem.objects.bulk_update(items, ["fifo_cost"])
    Transaction.objects.filter(sale=sale).delete()
    sale.posted = False
    sale.save(update_fields=["posted"])

    # Если в заказе был промокод, откатываем счетчик использований
    if sale.promo_code:
        # Уменьшаем атомарно, чтобы не уйти в минус
        PromoCode.objects.filter(
            id=sale.promo_code.id,
            used_count__gt=0,  # Защита: отнимаем только если больше нуля
        ).update(used_count=F("used_count") - 1)
