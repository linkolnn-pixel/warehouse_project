import pandas as pd
from decimal import Decimal, InvalidOperation
from django.db import transaction
from rest_framework.viewsets import ModelViewSet

from .models import Product, Category, Counterparty, Receipt, Sale, Transaction
from .exceptions import ExcelImportError, DocumentAlreadyPostedError, InvalidQuantityError, InsufficientStockError


@transaction.atomic
def import_products_from_excel(file_obj) -> tuple[int, int]:
    """
    Парсинг Excel-файла и создание товары, категории и поставщиков.
    Обернуто в @transaction.atomic: если произойдет сбой, ни один товар 
    не будет создан (база данных откатится к исходному состоянию).
    Возвращает кортеж: (количество_созданных, количество_пропущенных)
    """
    try:
        df = pd.read_excel(file_obj)
    except Exception as e:
        raise ExcelImportError(f"Не удалось прочитать файл Excel: {str(e)}")

    # Нормализация заголовков
    df.columns = df.columns.str.strip().str.lower()
    required_cols = ['наименование', 'закупочная цена', 'цена продажи']
    missing = [col for col in required_cols if col not in df.columns]

    if missing:
        raise ExcelImportError(f"В файле не найдены колонки: {', '.join(missing)}")

    categories_cache = {c.name: c for c in Category.objects.all()}
    suppliers_cache = {s.company_name: s for s in Counterparty.objects.filter(type='supplier')}

    existing_skus = set(Product.objects.exclude(sku='').values_list('sku', flat=True))
    existing_names = set(Product.objects.values_list('name', flat=True))

    products_to_create = []
    skip_count = 0

    for index, row in df.iterrows():
        # 1. Наименование
        name = str(row['наименование']).strip()
        if not name or name.lower() == 'nan':
            continue

        # 2. Артикул (SKU)
        sku_raw = row.get('артикул', '')
        sku = str(sku_raw).strip() if pd.notna(sku_raw) else ''

        # Проверка на дубликат через кэш
        if sku and sku in existing_skus:
            skip_count += 1
            continue
        if not sku and name in existing_names:
            skip_count += 1
            continue

        # 3. БРЕНД (КАТЕГОРИЯ)
        brand_val = row.get('бренд', '') or row.get('category_name', '')
        brand_name = str(brand_val).strip() if pd.notna(brand_val) else ''

        category_obj = None
        if brand_name:
            # Ищем в кэше, если нет - создаем и добавляем в кэш
            if brand_name not in categories_cache:
                cat = Category.objects.create(name=brand_name, parent=None)
                categories_cache[brand_name] = cat
            category_obj = categories_cache[brand_name]

        # 4. Цены
        try:
            cost_str = str(row['закупочная цена']).replace(',', '.')
            sale_str = str(row['цена продажи']).replace(',', '.')
            cost_price = Decimal(cost_str)
            sale_price = Decimal(sale_str)
        except (InvalidOperation, ValueError, TypeError):
            skip_count += 1
            continue  # Пропускаем строку с кривыми ценами

        # 5. Вес, объем, ед. изм.
        vol_raw = row.get('объем', 0)
        weight_raw = row.get('вес', 0)
        final_quantity = Decimal('0')
        final_measure = 'мл'
        final_unit = str(row.get('ед. изм.', 'шт')).strip().lower()

        if pd.notna(vol_raw) and str(vol_raw).lower() != 'nan':
            try:
                val = Decimal(str(vol_raw).replace(',', '.'))
                if val > 0:
                    final_quantity, final_measure = val, 'мл'
            except:
                pass
        elif pd.notna(weight_raw) and str(weight_raw).lower() != 'nan':
            try:
                val = Decimal(str(weight_raw).replace(',', '.'))
                if val > 0:
                    final_quantity, final_measure = val, 'г'
            except:
                pass

        # 6. Поставщик
        supplier_name_raw = row.get('поставщик', '') or row.get('supplier', '')
        supplier_name = str(supplier_name_raw).strip() if pd.notna(supplier_name_raw) and str(
            supplier_name_raw).lower() != 'nan' else ''

        supplier_obj = None
        if supplier_name:
            if supplier_name not in suppliers_cache:
                sup = Counterparty.objects.create(company_name=supplier_name, type='supplier')
                suppliers_cache[supplier_name] = sup
            supplier_obj = suppliers_cache[supplier_name]

        # 7. Формируем объект товара, НО НЕ СОХРАНЯЕМ В БД СРАЗУ
        product = Product(
            name=name,
            category=category_obj,
            supplier=supplier_obj,
            sku=sku,
            unit=final_unit,
            cost_price=cost_price,
            sale_price=sale_price,
            quantity_value=final_quantity,
            measure_unit=final_measure
        )
        products_to_create.append(product)

    # Сохраняем все валидные товары одним SQL-запросом!
    if products_to_create:
        Product.objects.bulk_create(products_to_create)

    return len(products_to_create), skip_count


@transaction.atomic
def post_receipt_document(receipt: Receipt):
    """Проведение прихода (Receipt)"""
    # Блокируем документ от одновременных изменений
    receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)

    if receipt.posted:
        raise DocumentAlreadyPostedError("Приход", receipt.number)

    for item in receipt.items.all():
        if item.quantity <= 0:
            raise InvalidQuantityError(item.product.name)

        # 1. Создаем транзакцию
        Transaction.objects.create(
            product=item.product,
            warehouse=receipt.warehouse,
            counterparty=receipt.supplier,
            type="IN",
            quantity=item.quantity,
            receipt=receipt,
            comment=f"Приход №{receipt.number}"
        )

        # 2. Обновляем цены товара
        item.product.cost_price = item.cost_price
        item.product.sale_price = item.sale_price
        item.product.save(update_fields=['cost_price', 'sale_price'])

    receipt.posted = True
    receipt.save(update_fields=['posted'])


@transaction.atomic
def post_sale_document(sale: Sale):
    """Проведение продажи (Sale)"""
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if sale.posted:
        raise DocumentAlreadyPostedError("Продажа", sale.number)

    quantities = {}
    for item in sale.items.all():
        if item.quantity <= 0:
            raise InvalidQuantityError(item.product.name)
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    # Проверяем остатки
    for product_id, quantity in quantities.items():
        product = Product.objects.select_for_update().get(pk=product_id)
        balance = product.get_balance(sale.warehouse)

        if quantity > balance:
            raise InsufficientStockError(product.name, balance, quantity)

    # Создаем транзакции расхода
    for product_id, quantity in quantities.items():
        product = Product.objects.get(pk=product_id)
        Transaction.objects.create(
            product=product,
            warehouse=sale.warehouse,
            counterparty=sale.customer,
            type="OUT",
            quantity=quantity,
            sale=sale,
            comment=f"Продажа №{sale.number}"
        )

    sale.posted = True
    sale.save(update_fields=["posted"])



