from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db import transaction

from .exceptions import (
    DocumentAlreadyPostedError,
    ExcelImportError,
    InsufficientStockError,
    InvalidQuantityError,
)
from .models import (
    Category,
    Counterparty,
    Product,
    Receipt,
    Sale,
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

    suppliers_cache = {supplier.company_name: supplier for supplier in Counterparty.objects.filter(type="supplier")}

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
                supplier_obj = Counterparty.objects.create(
                    company_name=supplier_name,
                    type="supplier",
                )

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


@transaction.atomic
def process_receipt_post(receipt: Receipt):
    """
    Проведение прихода.
    - Блокирует документ.
    - Проверяет количество.
    - Блокирует все товары в стабильном порядке.
    - Создает IN-транзакции.
    - Обновляет закупочную/продажную цену.
    """
    # 1. Блокируем документ самым первым действием.
    receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)

    if receipt.posted:
        raise DocumentAlreadyPostedError("Приход", receipt.number)

    # 2. Загружаем позиции один раз.
    items = list(receipt.items.select_related("product"))

    # 3. Проверяем количества до изменения БД.
    for item in items:
        if item.quantity <= 0:
            raise InvalidQuantityError(item.product.name)

    # 4. Получаем уникальные ID товаров
    #    и сортируем их для стабильного порядка блокировок.
    product_ids = sorted({item.product_id for item in items})

    # 5. Блокируем товары.
    locked_products = {
        product.id: product for product in (Product.objects.select_for_update().filter(id__in=product_ids))
    }

    # Защита от ситуации, когда товар был удален/не найден.
    if len(locked_products) != len(product_ids):
        missing_ids = set(product_ids) - set(locked_products)
        raise ValueError(f"Не найдены товары: {sorted(missing_ids)}")

    transactions = []
    products_to_update = []

    # 6. Формируем движения.
    for item in items:
        product = locked_products[item.product_id]

        transactions.append(
            Transaction(
                date=receipt.date,
                type="IN",
                product=product,
                warehouse=receipt.warehouse,
                counterparty=receipt.supplier,
                quantity=item.quantity,
                receipt=receipt,
                comment=f"Приход №{receipt.number}",
            )
        )

        # Обновляем текущие цены товара.
        product.cost_price = item.cost_price
        product.sale_price = item.sale_price

        products_to_update.append(product)

    # 7. Массово создаем движения.
    if transactions:
        Transaction.objects.bulk_create(transactions)

    # 8. Массово обновляем цены.
    if products_to_update:
        Product.objects.bulk_update(products_to_update, ["cost_price", "sale_price"])

    # 9. Завершаем проведение.
    receipt.posted = True
    receipt.save(update_fields=["posted"])


@transaction.atomic
def process_receipt_unpost(receipt: Receipt):
    """
    Отмена проведения прихода.
    Удаляет созданные этим документом IN-транзакции
    и переводит документ обратно в состояние draft.
    """
    receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)

    if not receipt.posted:
        raise ValueError(f"Приход №{receipt.number} не проведен.")

    Transaction.objects.filter(receipt=receipt).delete()

    receipt.posted = False
    receipt.save(update_fields=["posted"])


@transaction.atomic
def process_sale_post(sale: Sale):
    """
    Проведение продажи.
    - Блокирует документ.
    - Проверяет позиции.
    - Группирует одинаковые товары.
    - Блокирует товары в стабильном порядке.
    - Проверяет остатки.
    - Создает OUT-транзакции.
    """
    # 1. Сначала блокируем сам документ.
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if sale.posted:
        raise DocumentAlreadyPostedError("Продажа", sale.number)

    # 2. Загружаем позиции один раз.
    items = list(sale.items.select_related("product"))

    # 3. Проверяем количество и агрегируем товары.
    quantities: dict[int, int] = {}

    for item in items:
        if item.quantity <= 0:
            raise InvalidQuantityError(item.product.name)

        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    # 4. Блокируем товары в стабильном порядке.
    locked_products = {}

    for product_id in sorted(quantities):
        product = Product.objects.select_for_update().get(pk=product_id)

        quantity = quantities[product_id]

        balance = product.get_balance(sale.warehouse)

        if quantity > balance:
            raise InsufficientStockError(product.name, balance, quantity)

        locked_products[product_id] = product

    # 5. Создаем OUT-транзакции.
    transactions = [
        Transaction(
            date=sale.date,
            type="OUT",
            product=locked_products[item.product_id],
            warehouse=sale.warehouse,
            counterparty=sale.customer,
            quantity=item.quantity,
            sale=sale,
            comment=f"Продажа №{sale.number}",
        )
        for item in items
    ]

    if transactions:
        Transaction.objects.bulk_create(transactions)

    # 6. Завершаем проведение.
    sale.posted = True
    sale.save(update_fields=["posted"])


@transaction.atomic
def process_sale_unpost(sale: Sale):
    """
    Отмена проведения продажи.
    Удаляет созданные этим документом OUT-транзакции
    и переводит документ обратно в состояние draft.
    """
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if not sale.posted:
        raise ValueError(f"Продажа №{sale.number} не проведена.")

    Transaction.objects.filter(sale=sale).delete()

    sale.posted = False
    sale.save(update_fields=["posted"])
