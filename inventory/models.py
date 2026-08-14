from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify


class Warehouse(models.Model):
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Counterparty(models.Model):
    TYPE_CHOICES = (
        ('supplier', 'Поставщик'),
        ('customer', 'Клиент'),
    )
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES
    )

    # Поставщик
    company_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Название компании"
    )
    inn = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="ИНН"
    )

    # Клиент
    first_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Имя"
    )
    last_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Фамилия"
    )

    class Meta:
        verbose_name = 'Контрагент'
        verbose_name_plural = 'Контрагенты'

    def __str__(self):
        if self.type == 'customer':
            return f"{self.last_name} {self.first_name}"

        return self.company_name

class Category(models.Model):
    name = models.CharField(max_length=200, verbose_name="Название")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children',
                               verbose_name="Родительская категория")
    slug = models.SlugField(unique=True, blank=True)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        full_path = [self.name]
        k = self.parent
        while k is not None:
            full_path.append(k.name)
            k = k.parent
        return ' > '.join(full_path[::-1])


#  СЧЕТЧИК
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
        sequence.save(update_fields=['next_code'])
        return current_code


# -----------------------------

class Product(models.Model):
    sku = models.CharField(max_length=50, blank=True, null=True, default='', verbose_name="Артикул")
    internal_code = models.CharField(max_length=20, unique=True, verbose_name="Внутренний код")
    name = models.CharField(max_length=200, verbose_name="Наименование")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Категория")
    brand = models.CharField(max_length=100, blank=True, null=True, verbose_name="Бренд", db_index=True)
    unit = models.CharField(max_length=20, default="шт", verbose_name="Ед. измерения")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Закупочная цена")
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Цена продажи")
    quantity_value = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                         verbose_name="Значение (вес/объем)")

    MEASURE_CHOICES = [
        ('мл', 'мл (миллилитры)'),
        ('г', 'г (граммы)'),
    ]
    measure_unit = models.CharField(max_length=10, choices=MEASURE_CHOICES, default="мл",
                                    verbose_name="Ед. изм. (вес/объем)")
    supplier = models.ForeignKey(Counterparty, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='supplied_products', verbose_name="Поставщик")

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ['brand', 'name']

    def __str__(self):
        return self.name

    @property
    def profit(self):
        # Прибыль с одной единицы товара
        return self.sale_price - self.cost_price

    def get_balance(self, warehouse):
        from django.db.models import Sum

        in_sum = self.transactions.filter(
            warehouse=warehouse,
            type='IN'
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0

        out_sum = self.transactions.filter(
            warehouse=warehouse,
            type='OUT'
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0

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
        ('IN', 'Приход'),
        ('OUT', 'Расход'),
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='transactions')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='transactions')
    counterparty = models.ForeignKey(Counterparty, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='transactions')
    type = models.CharField(max_length=3, choices=TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    date = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True)
    receipt = models.ForeignKey(
        'Receipt',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    sale = models.ForeignKey(
        'Sale',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ['-date']
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
    number = models.PositiveIntegerField(
        unique=True,
        editable=False
    )
    date = models.DateTimeField(
        auto_now_add=True
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT
    )
    supplier = models.ForeignKey(
        Counterparty,
        on_delete=models.PROTECT,
        limit_choices_to={'type': 'supplier'}
    )
    comment = models.TextField(blank=True)
    posted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):

        if not self.number:
            last = Receipt.objects.order_by(
                "-number"
            ).first()
            self.number = (last.number + 1) if last else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Приход №{self.number}"

    @transaction.atomic
    def post(self):
        if self.posted:
            return
        for item in self.items.all():
            Transaction.objects.create(
                product=item.product,
                warehouse=self.warehouse,
                counterparty=self.supplier,
                type="IN",
                quantity=item.quantity,
                receipt=self,
                comment=f"Приход №{self.number}"
            )
            # обновляем закупочную цену
            # обновляем цены товара после прихода
            item.product.cost_price = item.cost_price
            item.product.sale_price = item.sale_price
            item.product.save(
                update_fields=[
                    'cost_price',
                    'sale_price'
                ]
            )
        self.posted = True
        self.save(update_fields=['posted'])

class ReceiptItem(models.Model):
    receipt = models.ForeignKey(
        Receipt,
        related_name="items",
        on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )
    quantity = models.PositiveIntegerField()
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    @property
    def total_cost(self):
        return self.quantity * self.cost_price

    @property
    def total_sale(self):
        return self.quantity * self.sale_price

class Sale(models.Model):
    number = models.PositiveIntegerField(
        unique=True,
        editable=False
    )
    date = models.DateTimeField(auto_now_add=True)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT
    )
    customer = models.ForeignKey(
        Counterparty,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        limit_choices_to={'type': 'customer'}
    )
    comment = models.TextField(blank=True)
    posted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.number:
            last = Sale.objects.order_by(
                "-number"
            ).first()
            self.number = (last.number + 1) if last else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Продажа №{self.number}"

    @transaction.atomic
    def post(self):
        if self.posted:
            return

        # Блокируем саму продажу
        sale = (
            Sale.objects
            .select_for_update()
            .get(pk=self.pk)
        )

        if sale.posted:
            return

        # Собираем количество по товарам.
        # Если один товар случайно указан несколько раз,
        # его количества суммируются.
        quantities = {}

        for item in sale.items.all():
            if item.quantity <= 0:
                raise ValidationError(
                    f"Количество товара «{item.product.name}» "
                    f"должно быть больше 0."
                )

            quantities[item.product_id] = (
                    quantities.get(item.product_id, 0)
                    + item.quantity
            )

        # Проверяем остатки
        for product_id, quantity in quantities.items():

            product = (
                Product.objects
                .select_for_update()
                .get(pk=product_id)
            )

            balance = product.get_balance(sale.warehouse)

            if quantity > balance:
                raise ValidationError(
                    f"Недостаточно товара: {product.name}. "
                    f"Доступно: {balance} шт., "
                    f"запрошено: {quantity} шт."
                )

        # Создаём расходные операции
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

        # Проведение продажи
        sale.posted = True
        sale.save(update_fields=["posted"])

        # Обновляем текущий объект
        self.posted = True


class SaleItem(models.Model):
    sale = models.ForeignKey(
        Sale,
        related_name="items",
        on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )
    quantity = models.PositiveIntegerField()
    sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    @property
    def total(self):
        return self.quantity * self.sale_price