from decimal import Decimal

from django.test import TestCase

from inventory.exceptions import DocumentAlreadyPostedError, InsufficientStockError
from inventory.models import (
    Category,
    Counterparty,
    Product,
    Receipt,
    ReceiptItem,
    Sale,
    SaleItem,
    Transaction,
    Warehouse,
)
from inventory.services import (
    process_receipt_post,
    process_receipt_unpost,
    process_sale_post,
)


class StockBalanceTestCase(TestCase):
    def setUp(self):
        # Подготавливаем чистые данные для теста
        self.warehouse = Warehouse.objects.create(name="Основной склад")

        self.supplier = Counterparty.objects.create(type="supplier", company_name="Поставщик ООО")
        self.customer = Counterparty.objects.create(type="customer", first_name="Иван", last_name="Иванов")

        # ИСПРАВЛЕНО: убрали несуществующее поле type
        self.product = Product.objects.create(name="Ceramide repair cream 50 мл")

    def test_stock_balances_after_receipt_and_sale(self):
        # 1. СОЗДАЕМ ПРИХОД НА 10 ШТУК
        receipt = Receipt.objects.create(warehouse=self.warehouse, supplier=self.supplier)
        ReceiptItem.objects.create(receipt=receipt, product=self.product, quantity=10, cost_price=1000, sale_price=1500)

        # 2. ПРОВЕРЯЕМ ДО ПРОВЕДЕНИЯ (должен быть 0)
        balance_before = self.product.get_balance(self.warehouse)
        self.assertEqual(balance_before, 0, "Остаток до проведения прихода должен быть 0")

        # 3. ПРОВОДИМ ПРИХОД
        process_receipt_post(receipt)

        # Выводим транзакции для отладки
        transactions = list(Transaction.objects.values("type", "quantity", "warehouse__name"))
        print(f"\n--- ТРАНЗАКЦИИ ПОСЛЕ ПРИХОДА ---\n{transactions}")

        # 4. ПРОВЕРЯЕМ ОСТАТОК ПОСЛЕ ПРОВЕДЕНИЯ (должен стать 10)
        balance_after = self.product.get_balance(self.warehouse)
        self.assertEqual(
            balance_after,
            10,
            f"Ошибка! Остаток не 10. Метод расчета вернул: {balance_after}. Посмотрите транзакции выше.",
        )

        # 5. СОЗДАЕМ И ПРОВОДИМ ПРОДАЖУ НА 1 ШТУКУ
        sale = Sale.objects.create(warehouse=self.warehouse, customer=self.customer)
        SaleItem.objects.create(sale=sale, product=self.product, quantity=1, sale_price=1500)
        process_sale_post(sale)

        # 6. ПРОВЕРЯЕМ ФИНАЛЬНЫЙ ОСТАТОК (должен стать 9)
        balance_final = self.product.get_balance(self.warehouse)
        self.assertEqual(balance_final, 9, "Остаток после продажи 1 шт должен стать 9")


class InventoryServicesTests(TestCase):
    def setUp(self):
        """Создаем базовые данные для всех тестов (склад, клиенты, товары)"""
        self.warehouse = Warehouse.objects.create(name="Основной склад")

        self.supplier = Counterparty.objects.create(type="supplier", company_name="ООО Ромашка", inn="1234567890")
        self.customer = Counterparty.objects.create(type="customer", first_name="Иван", last_name="Иванов")

        self.category = Category.objects.create(name="Напитки")

        self.product = Product.objects.create(
            name="Сок Яблочный",
            category=self.category,
            supplier=self.supplier,
            cost_price=Decimal("50.00"),
            sale_price=Decimal("100.00"),
        )

    # ==========================
    # ТЕСТЫ ПРИХОДА (RECEIPT)
    # ==========================

    def test_receipt_post_success(self):
        """Успешное проведение прихода: создаются транзакции, обновляются цены, растет остаток."""
        receipt = Receipt.objects.create(warehouse=self.warehouse, supplier=self.supplier)
        ReceiptItem.objects.create(
            receipt=receipt,
            product=self.product,
            quantity=10,
            cost_price=Decimal("60.00"),
            sale_price=Decimal("120.00"),
        )

        process_receipt_post(receipt)

        # Проверяем статус документа
        receipt.refresh_from_db()
        self.assertTrue(receipt.posted)

        # Проверяем, что появилась 1 транзакция IN
        tx_count = Transaction.objects.filter(receipt=receipt, type="IN").count()
        self.assertEqual(tx_count, 1)

        # Проверяем, что остаток стал 10
        self.assertEqual(self.product.get_balance(self.warehouse), 10)

        # Проверяем, что цены товара обновились из прихода
        self.product.refresh_from_db()
        self.assertEqual(self.product.cost_price, Decimal("60.00"))
        self.assertEqual(self.product.sale_price, Decimal("120.00"))

    def test_receipt_double_post_error(self):
        """Защита от двойного проведения прихода."""
        receipt = Receipt.objects.create(warehouse=self.warehouse, supplier=self.supplier)
        ReceiptItem.objects.create(
            receipt=receipt,
            product=self.product,
            quantity=10,
            cost_price=Decimal("50.00"),
            sale_price=Decimal("100.00"),
        )

        # Первое проведение
        process_receipt_post(receipt)

        # Второе проведение должно выбросить ошибку
        with self.assertRaises(DocumentAlreadyPostedError):
            process_receipt_post(receipt)

    def test_receipt_unpost(self):
        """Отмена проведения прихода: транзакции удаляются, остаток падает."""
        receipt = Receipt.objects.create(warehouse=self.warehouse, supplier=self.supplier)
        ReceiptItem.objects.create(
            receipt=receipt,
            product=self.product,
            quantity=10,
            cost_price=Decimal("50.00"),
            sale_price=Decimal("100.00"),
        )
        process_receipt_post(receipt)

        # Отменяем
        process_receipt_unpost(receipt)

        receipt.refresh_from_db()
        self.assertFalse(receipt.posted)
        self.assertEqual(Transaction.objects.filter(receipt=receipt).count(), 0)
        self.assertEqual(self.product.get_balance(self.warehouse), 0)

    # ==========================
    # ТЕСТЫ ПРОДАЖИ (SALE)
    # ==========================

    def test_sale_insufficient_stock(self):
        """Попытка продать товар, которого нет на складе, должна вызывать ошибку."""
        sale = Sale.objects.create(warehouse=self.warehouse, customer=self.customer)
        SaleItem.objects.create(sale=sale, product=self.product, quantity=5, sale_price=Decimal("100.00"))

        # На складе 0 штук, пытаемся продать 5
        with self.assertRaises(InsufficientStockError):
            process_sale_post(sale)

    def test_sale_post_success(self):
        """Успешное проведение продажи (при наличии остатков)."""
        # Сначала делаем приход на 10 штук
        receipt = Receipt.objects.create(warehouse=self.warehouse, supplier=self.supplier)
        ReceiptItem.objects.create(
            receipt=receipt,
            product=self.product,
            quantity=10,
            cost_price=Decimal("50.00"),
            sale_price=Decimal("100.00"),
        )
        process_receipt_post(receipt)

        # Теперь продаем 3 штуки
        sale = Sale.objects.create(warehouse=self.warehouse, customer=self.customer)
        SaleItem.objects.create(sale=sale, product=self.product, quantity=3, sale_price=Decimal("120.00"))
        process_sale_post(sale)

        sale.refresh_from_db()
        self.assertTrue(sale.posted)

        # Остаток должен стать 10 - 3 = 7
        self.assertEqual(self.product.get_balance(self.warehouse), 7)

    def test_sale_multiple_same_products(self):
        """Проверка агрегации: если один и тот же товар добавлен в продажу двумя строками."""
        # Приходуем 10 штук
        receipt = Receipt.objects.create(warehouse=self.warehouse, supplier=self.supplier)
        ReceiptItem.objects.create(
            receipt=receipt,
            product=self.product,
            quantity=10,
            cost_price=Decimal("50.00"),
            sale_price=Decimal("100.00"),
        )
        process_receipt_post(receipt)

        sale = Sale.objects.create(warehouse=self.warehouse, customer=self.customer)
        # Строка 1: продаем 4 штуки
        SaleItem.objects.create(sale=sale, product=self.product, quantity=4, sale_price=Decimal("100.00"))
        # Строка 2: продаем еще 7 штук (итого 11)
        SaleItem.objects.create(sale=sale, product=self.product, quantity=7, sale_price=Decimal("100.00"))

        # Должна вылететь ошибка нехватки (нужно 11, а на складе 10),
        # это доказывает, что наша группировка работает!
        with self.assertRaises(InsufficientStockError):
            process_sale_post(sale)
