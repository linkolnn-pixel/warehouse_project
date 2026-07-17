from django.contrib import admin
from .models import Warehouse, Product, Counterparty, Transaction


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'address')
    search_fields = ('name',)


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'inn')
    list_filter = ('type',)  # Фильтр по типу: Поставщик / Клиент
    search_fields = ('name', 'inn')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'category', 'unit', 'price')
    list_filter = ('category', 'unit')
    search_fields = ('sku', 'name')
    ordering = ('name',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    # Что видно в списке операций
    list_display = ('get_type_display', 'product', 'warehouse', 'quantity', 'date', 'counterparty')

    # Фильтры для быстрой выборки в админке
    list_filter = ('type', 'warehouse', 'date', 'product__category')

    # Поиск по товару или контрагенту
    search_fields = ('product__name', 'counterparty__name')

    # Группировка по дате в сайдбаре
    date_hierarchy = 'date'

    # Поля, которые можно редактировать прямо в списке (быстрое изменение кол-ва, например)
    readonly_fields = ('date',)

    # Опционально: если нужно видеть баланс товара прямо в карточке операции (требует доп. логики)
    # def get_balance_display(self, obj):
    #     return obj.product.get_balance(obj.warehouse)
    # get_balance_display.short_description = 'Текущий остаток'
    # list_display += ('get_balance_display',)
