from django.contrib import admin
from .models import Warehouse, Product, Counterparty, Transaction, Category

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'address')
    search_fields = ('name',)


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = (
        'company_name',
        'first_name',
        'last_name',
        'type',
        'inn'
    )

    list_filter = ('type',)

    search_fields = (
        'company_name',
        'first_name',
        'last_name',
        'inn',
    )

    def delete_model(self, request, obj):
        from .models import Receipt, Sale, Transaction
        Receipt.objects.filter(supplier=obj).delete()
        Sale.objects.filter(customer=obj).delete()
        Transaction.objects.filter(counterparty=obj).delete()
        obj.delete()

    def delete_queryset(self, request, queryset):
        from .models import Receipt, Sale, Transaction
        for counterparty in queryset:
            Receipt.objects.filter(supplier=counterparty).delete()
            Sale.objects.filter(customer=counterparty).delete()
            Transaction.objects.filter(counterparty=counterparty).delete()
        queryset.delete()

    def get_deleted_objects(self, objs, request):
        deleted_objects = []
        model_count = {}
        perms_needed = set()
        protected = []

        return deleted_objects, model_count, perms_needed, protected


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'internal_code',
        'sku',
        'name',
        'category',
        'supplier',
        'cost_price',
        'sale_price',
        'quantity_value',
        'measure_unit'
    )

    list_filter = ('category', 'unit')
    search_fields = ('sku', 'name')
    ordering = ('name',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['internal_code'].required = False
        return form

    def delete_model(self, request, obj):
        from .models import ReceiptItem, SaleItem

        ReceiptItem.objects.filter(product=obj).delete()
        SaleItem.objects.filter(product=obj).delete()

        obj.delete()

    def delete_queryset(self, request, queryset):
        from .models import ReceiptItem, SaleItem

        for product in queryset:
            ReceiptItem.objects.filter(product=product).delete()
            SaleItem.objects.filter(product=product).delete()

        queryset.delete()

    def get_deleted_objects(self, objs, request):
        # Отключаем блокировку PROTECT в админке
        deleted_objects = []
        model_count = {}
        perms_needed = set()
        protected = []

        return deleted_objects, model_count, perms_needed, protected


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'slug')
    list_filter = ('parent',)
    search_fields = ('name',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'type', 'quantity', 'date', 'counterparty')
    list_filter = ('type', 'warehouse')
    search_fields = (
        'product__name',
        'counterparty__company_name',
        'counterparty__first_name',
        'counterparty__last_name',
    )

    date_hierarchy = 'date'

    readonly_fields = ('date',)


