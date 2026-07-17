from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

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
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    inn = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'Контрагент'
        verbose_name_plural = 'Контрагенты'

    def __str__(self):
        return f"{self.get_type_display()} — {self.name}"

class Product(models.Model):
    sku = models.CharField(max_length=50, unique=True, verbose_name="Артикул")
    name = models.CharField(max_length=200, verbose_name="Наименование")
    category = models.CharField(max_length=100, blank=True, verbose_name="Категория")
    unit = models.CharField(max_length=20, default="шт", verbose_name="Ед. измерения")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Цена")

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    def __str__(self):
        return f"{self.sku} — {self.name}"

    def get_balance(self, warehouse):
        from django.db.models import Sum
        in_sum = self.transactions.filter(warehouse=warehouse, type='IN').aggregate(Sum('quantity'))['quantity__sum'] or 0
        out_sum = self.transactions.filter(warehouse=warehouse, type='OUT').aggregate(Sum('quantity'))['quantity__sum'] or 0
        return in_sum - out_sum

class Transaction(models.Model):
    TYPE_CHOICES = (
        ('IN', 'Приход'),
        ('OUT', 'Расход'),
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='transactions')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='transactions')
    counterparty = models.ForeignKey(Counterparty, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    type = models.CharField(max_length=3, choices=TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    date = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "Операция"
        verbose_name_plural = "Операции"

    def clean(self):
        if self.type == 'OUT':
            current_balance = self.product.get_balance(self.warehouse)
            if self.quantity > current_balance:
                raise ValidationError(_("Недостаточно товара. Текущий остаток: %(balance)s"), params={'balance': current_balance})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_type_display()} {self.product.name} ({self.quantity} {self.product.unit})"
