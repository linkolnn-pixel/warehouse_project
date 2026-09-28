from django.contrib import admin

from .models import Category, Counterparty, Product, Transaction, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "address")
    search_fields = ("name",)


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ("company_name", "first_name", "last_name", "type", "inn", "is_deleted")

    list_filter = ("type", "is_deleted")

    search_fields = (
        "company_name",
        "first_name",
        "last_name",
        "inn",
    )

    def get_deleted_objects(self, objs, request):
        deleted_objects = []
        model_count = {}
        perms_needed = set()
        protected = []

        return deleted_objects, model_count, perms_needed, protected


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "internal_code",
        "sku",
        "name",
        "category",
        "supplier",
        "cost_price",
        "sale_price",
        "quantity_value",
        "measure_unit",
        "is_deleted",
    )

    list_filter = ("category", "unit", "is_deleted")
    search_fields = ("sku", "name")
    ordering = ("name",)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["internal_code"].required = False
        return form

    def get_deleted_objects(self, objs, request):
        # Отключаем блокировку PROTECT в админке
        deleted_objects = []
        model_count = {}
        perms_needed = set()
        protected = []

        return deleted_objects, model_count, perms_needed, protected


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "slug")
    list_filter = ("parent",)
    search_fields = ("name",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "type", "quantity", "date", "counterparty")
    list_filter = ("type", "warehouse")
    search_fields = (
        "product__name",
        "counterparty__company_name",
        "counterparty__first_name",
        "counterparty__last_name",
    )

    date_hierarchy = "date"

    readonly_fields = ("date",)
