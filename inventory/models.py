from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel

from inventory.managers import ActiveManager, ProductManager


class StockBalance(models.Model):
    product = models.ForeignKey("Product", on_delete=models.CASCADE, related_name="balances")
    warehouse = models.ForeignKey("Warehouse", on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Остаток на складе"
        verbose_name_plural = "Остатки на складах"
        # Уникальный индекс гарантирует одну запись на пару товар-склад
        constraints = [models.UniqueConstraint(fields=["product", "warehouse"], name="unique_stock_balance")]

    def __str__(self):
        return f"{self.product.name} - {self.warehouse.name}: {self.quantity}"


class SoftDeleteModel(models.Model):  # mixin
    """
    Абстрактная модель. Миксин.
    Вместо физического удаления ставит галочку is_deleted = True.
    """

    is_deleted = models.BooleanField(default=False, verbose_name="Удален")

    # Переопределяем стандартный objects, чтобы он отдавал только "живые" записи
    objects = ActiveManager()
    # Оставляем доступ ко всем записям (включая удаленные) для админки и отчетов
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Мягкое удаление (скрытие)"""
        self.is_deleted = True
        self.save(update_fields=["is_deleted"])

    def hard_delete(self):
        """Реальное удаление из БД"""
        super().delete()


class Warehouse(models.Model):
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Supplier(SoftDeleteModel):
    company_name = models.CharField(max_length=200)
    inn = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        verbose_name = "Поставщик"
        verbose_name_plural = "Поставщики"

    def __str__(self):
        return self.company_name


class Customer(SoftDeleteModel):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"

    def __str__(self):
        return f"{self.last_name} {self.first_name}"


class Category(MPTTModel):
    name = models.CharField(max_length=200, verbose_name="Название")
    parent = TreeForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Родительская категория",
    )
    slug = models.SlugField(unique=True, blank=True)

    class MPTTMeta:
        order_insertion_by = ["name"]

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    def __str__(self):
        ancestors = self.get_ancestors(include_self=True)
        return " > ".join([a.name for a in ancestors])


class ProductCodeSequence(models.Model):
    next_code = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Счетчик кодов товаров"
        verbose_name_plural = "Счетчики кодов товаров"

    @classmethod
    @transaction.atomic
    def get_next_code(cls):
        # Блокируем строку, чтобы никто другой не мог её читать/писать пока мы работаем
        sequence, created = cls.objects.select_for_update().get_or_create(pk=1)
        current_code = sequence.next_code
        sequence.next_code += 1
        sequence.save(update_fields=["next_code"])
        return current_code


class DocumentSequence(models.Model):
    document_type = models.CharField(max_length=50, unique=True, verbose_name="Тип документа")
    last_number = models.PositiveIntegerField(default=0, verbose_name="Последний номер")

    class Meta:
        verbose_name = "Счетчик документов"
        verbose_name_plural = "Счетчики документов"

    @classmethod
    @transaction.atomic
    def get_next_number(cls, doc_type: str) -> int:
        # Блокируем строку конкретного типа документа
        sequence, created = cls.objects.select_for_update().get_or_create(
            document_type=doc_type, defaults={"last_number": 0}
        )
        sequence.last_number += 1
        sequence.save(update_fields=["last_number"])
        return sequence.last_number


class Product(SoftDeleteModel):
    sku = models.CharField(max_length=50, blank=True, null=True, default="", verbose_name="Артикул")
    internal_code = models.CharField(max_length=20, unique=True, verbose_name="Внутренний код")
    name = models.CharField(max_length=200, verbose_name="Наименование")
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Категория",
    )
    brand = models.CharField(max_length=100, blank=True, null=True, verbose_name="Бренд", db_index=True)
    unit = models.CharField(max_length=20, default="шт", verbose_name="Ед. измерения")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Закупочная цена")
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Цена продажи")
    quantity_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Значение (вес/объем)"
    )

    MEASURE_CHOICES = [
        ("мл", "мл (миллилитры)"),
        ("г", "г (граммы)"),
    ]
    measure_unit = models.CharField(
        max_length=10,
        choices=MEASURE_CHOICES,
        default="мл",
        verbose_name="Ед. изм. (вес/объем)",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplied_products",
        verbose_name="Поставщик",
    )
    average_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Средняя себестоимость")
    objects = ProductManager()  # type: ignore

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["brand", "name"]

    def __str__(self):
        return self.name

    def profit(self):
        # Прибыль с одной единицы товара
        return self.sale_price - self.cost_price

    def get_balance(self, warehouse):
        balance = self.balances.filter(warehouse=warehouse).first()
        return balance.quantity if balance else 0

    def get_stock_profit(self, warehouse):
        # Потенциальная прибыль со всего остатка
        balance = self.get_balance(warehouse)

        return balance * self.profit()

    def save(self, *args, **kwargs):
        # Если код еще не установлен (новый товар)
        if not self.internal_code:
            # Получаем уникальный номер из счетчика
            code_number = ProductCodeSequence.get_next_code()
            self.internal_code = f"{code_number:04d}"
        super().save(*args, **kwargs)


class Transaction(models.Model):
    TYPE_CHOICES = (
        ("IN", "Приход"),
        ("OUT", "Расход"),
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="transactions")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=3, choices=TYPE_CHOICES, db_index=True)
    quantity = models.PositiveIntegerField()
    date = models.DateTimeField(default=timezone.now, db_index=True)
    comment = models.TextField(blank=True)
    receipt = models.ForeignKey("Receipt", null=True, blank=True, on_delete=models.SET_NULL)
    sale = models.ForeignKey("Sale", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Операция"
        verbose_name_plural = "Операции"

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError(_("Количество должно быть больше 0"))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_type_display()} {self.product.name} ({self.quantity} {self.product.unit})"


class DocumentMixin(models.Model):
    """
    Миксин для всех документов движения товаров.
    Добавляет базовые поля и автоматическую генерацию номера.
    """

    number = models.PositiveIntegerField(unique=True, editable=False)
    date = models.DateTimeField(default=timezone.now)
    comment = models.TextField(blank=True)
    posted = models.BooleanField(default=False)

    class Meta:
        abstract = True  # Обязательно для миксинов с полями БД

    def get_document_type(self):
        # По умолчанию берем имя дочернего класса в нижнем регистре ('receipt', 'sale')
        return self.__class__.__name__.lower()

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentSequence.get_next_number(self.get_document_type())
        super().save(*args, **kwargs)


class Receipt(DocumentMixin):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, null=True)
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Стоимость доставки")

    def __str__(self):
        return f"Приход №{self.number}"

    @property
    def calculated_total(self):
        items_total = sum(item.total_cost for item in self.items.all())
        return items_total + self.delivery_cost


class ReceiptItem(models.Model):
    receipt = models.ForeignKey(Receipt, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def total_cost(self):
        return self.quantity * self.cost_price

    @property
    def total_sale(self):
        return self.quantity * self.sale_price


class Sale(DocumentMixin):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, null=True)
    delivery_expense = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Расходы на доставку"
    )

    def __str__(self):
        return f"Продажа №{self.number}"

    @property
    def net_profit(self):
        items_profit = sum((item.sale_price - item.cost_price) * item.quantity for item in self.items.all())
        return items_profit - self.delivery_expense

    @property
    def calculated_total(self):
        return sum(item.total for item in self.items.all())


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def total(self):
        return self.quantity * self.sale_price

    @property
    def total_cost(self):
        return self.quantity * self.cost_price

    @property
    def profit(self):
        return self.total - self.total_cost
