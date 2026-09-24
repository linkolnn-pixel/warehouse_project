from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel

from inventory.managers import ProductManager


class Warehouse(models.Model):
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Counterparty(models.Model):
    TYPE_CHOICES = (
        ("supplier", "Поставщик"),
        ("customer", "Клиент"),
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    # Поставщик
    company_name = models.CharField(max_length=200, blank=True, verbose_name="Название компании")
    inn = models.CharField(max_length=20, blank=True, null=True, verbose_name="ИНН")

    # Клиент
    first_name = models.CharField(max_length=100, blank=True, verbose_name="Имя")
    last_name = models.CharField(max_length=100, blank=True, verbose_name="Фамилия")

    class Meta:
        verbose_name = "Контрагент"
        verbose_name_plural = "Контрагенты"
        constraints = [
            models.UniqueConstraint(
                fields=["type", "first_name", "last_name"],
                condition=models.Q(type="customer"),
                name="unique_customer_name",
            ),
        ]

    def clean(self):
        super().clean()

        if self.type == "customer":
            if not self.first_name or not self.first_name.strip():
                raise ValidationError({"first_name": "Введите имя клиента."})

            if not self.last_name or not self.last_name.strip():
                raise ValidationError({"last_name": "Введите фамилию клиента."})

        elif self.type == "supplier":
            if not self.company_name or not self.company_name.strip():
                raise ValidationError({"company_name": "Введите название компании."})

            if not self.inn or not self.inn.strip():
                raise ValidationError({"inn": "Введите ИНН."})

    def __str__(self):
        if self.type == "customer":
            return f"{self.last_name} {self.first_name}"

        return self.company_name


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

    class MPTTMetta:
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


class Product(models.Model):
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
        Counterparty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplied_products",
        verbose_name="Поставщик",
    )
    objects = ProductManager()

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
        from django.db.models import Sum

        in_sum = self.transactions.filter(warehouse=warehouse, type="IN").aggregate(total=Sum("quantity"))["total"] or 0

        out_sum = (
            self.transactions.filter(warehouse=warehouse, type="OUT").aggregate(total=Sum("quantity"))["total"] or 0
        )

        return in_sum - out_sum

    def get_stock_profit(self, warehouse):
        # Потенциальная прибыль со всего остатка
        balance = self.get_balance(warehouse)

        return balance * self.profit

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
    counterparty = models.ForeignKey(
        Counterparty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    type = models.CharField(max_length=3, choices=TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    date = models.DateTimeField(auto_now_add=True)
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


class Receipt(models.Model):
    number = models.PositiveIntegerField(unique=True, editable=False)
    date = models.DateTimeField(auto_now_add=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    supplier = models.ForeignKey(Counterparty, on_delete=models.PROTECT, limit_choices_to={"type": "supplier"})
    comment = models.TextField(blank=True)
    posted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.number:
            last = Receipt.objects.order_by("-number").first()
            self.number = (last.number + 1) if last else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Приход №{self.number}"

    @transaction.atomic
    def post(self):
        receipt = Receipt.objects.select_for_update().get(pk=self.pk)

        if receipt.posted:
            return

        items = receipt.items.select_related("product").all()

        transactions_to_create = []
        products_to_update = []

        for item in items:
            # Подготавливаем транзакции в памяти (без отправки в БД)
            transactions_to_create.append(
                Transaction(
                    product=item.product,
                    warehouse=receipt.warehouse,
                    counterparty=receipt.supplier,
                    type="IN",
                    quantity=item.quantity,
                    receipt=receipt,
                    comment=f"Приход №{receipt.number}",
                )
            )
            # Обновляем цены товара в оперативной памяти
            item.product.cost_price = item.cost_price
            item.product.sale_price = item.sale_price
            products_to_update.append(item.product)

        # Сохраняем все транзакции ОДНИМ запросом
        if transactions_to_create:
            Transaction.objects.bulk_create(transactions_to_create)

        # Сохраняем новые цены для всех товаров ОДНИМ запросом
        if products_to_update:
            Product.objects.bulk_update(products_to_update, fields=["cost_price", "sale_price"])
        # Помечаем документ как проведенный
        receipt.posted = True
        receipt.save(update_fields=["posted"])

        # Обновляем состояние текущего инстанса, с которым мы работаем
        self.posted = True

    @transaction.atomic
    def unpost(self):
        if not self.posted:
            return

        # Удаляем все приходы по этому документу
        Transaction.objects.filter(receipt=self).delete()

        self.posted = False
        self.save(update_fields=["posted"])


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


class Sale(models.Model):
    number = models.PositiveIntegerField(unique=True, editable=False)
    date = models.DateTimeField(auto_now_add=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    customer = models.ForeignKey(
        Counterparty,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        limit_choices_to={"type": "customer"},
    )
    comment = models.TextField(blank=True)
    posted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.number:
            last = Sale.objects.order_by("-number").first()
            self.number = (last.number + 1) if last else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Продажа №{self.number}"

    @transaction.atomic
    def post(self):
        if self.posted:
            return

        sale = Sale.objects.select_for_update().get(pk=self.pk)
        if sale.posted:
            return

        quantities: dict = {}
        for item in sale.items.all():
            if item.quantity <= 0:
                raise ValidationError(f"Количество товара «{item.product.name}» должно быть больше 0.")
            quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

        # 1. Забираем ВСЕ нужные товары и блокируем их разом (один запрос в БД)
        locked_products = {p.id: p for p in Product.objects.select_for_update().filter(id__in=quantities.keys())}

        # 2. Проверяем остатки
        for product_id, quantity in quantities.items():
            product = locked_products[product_id]
            balance = product.get_balance(sale.warehouse)

            if quantity > balance:
                raise ValidationError(
                    f"Недостаточно товара: {product.name}. " f"Доступно: {balance} шт., запрошено: {quantity} шт."
                )

        # 3. Подготавливаем транзакции в памяти
        new_transactions = []
        for product_id, quantity in quantities.items():
            new_transactions.append(
                Transaction(
                    product=locked_products[product_id],
                    warehouse=sale.warehouse,
                    counterparty=sale.customer,
                    type="OUT",
                    quantity=quantity,
                    sale=sale,
                    comment=f"Продажа №{sale.number}",
                )
            )

        # 4. Сохраняем все транзакции ОДНИМ запросом в БД
        Transaction.objects.bulk_create(new_transactions)

        sale.posted = True
        sale.save(update_fields=["posted"])
        self.posted = True

    @transaction.atomic
    def unpost(self):
        if not self.posted:
            return

        # Удаляем все движения по складу, связанные с этой продажей
        Transaction.objects.filter(sale=self).delete()

        self.posted = False
        self.save(update_fields=["posted"])


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def total(self):
        return self.quantity * self.sale_price
