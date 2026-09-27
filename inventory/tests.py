from django.test import TestCase

from inventory.models import Counterparty, Product, Receipt, ReceiptItem, Sale, SaleItem, Transaction, Warehouse
from inventory.services import process_receipt_post, process_sale_post


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
