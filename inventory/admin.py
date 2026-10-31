from django.contrib import admin
from django.db.models import Sum

from .models import Category, Customer, Product, StockBalance, Supplier, Transaction, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "address")
    search_fields = ("name",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("company_name", "inn", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("company_name", "inn")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("first_name", "last_name")


@admin.action(description="Пересчитать остатки")
def recalculate_stock(modeladmin, request, queryset):
    for product in queryset:
        for warehouse in Warehouse.objects.all():
            in_qty = (
                Transaction.objects.filter(product=product, warehouse=warehouse, type="IN").aggregate(Sum("quantity"))[
                    "quantity__sum"
                ]
                or 0
            )

            out_qty = (
                Transaction.objects.filter(product=product, warehouse=warehouse, type="OUT").aggregate(Sum("quantity"))[
                    "quantity__sum"
                ]
                or 0
            )

            StockBalance.objects.update_or_create(
                product=product, warehouse=warehouse, defaults={"quantity": in_qty - out_qty}
            )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    actions = [recalculate_stock]
    list_display = (
        "internal_code",
        "sku",
        "name",
        "brand",
        "category",
        "supplier",
        "cost_price",
        "sale_price",
        "quantity_value",
        "measure_unit",
        "is_deleted",
    )
    list_filter = ("category", "brand", "unit", "is_deleted")
    search_fields = ("sku", "name", "brand")
    ordering = ("name",)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["internal_code"].required = False
        return form


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "slug")
    list_filter = ("parent",)
    search_fields = ("name",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "type", "quantity", "date", "get_counterparty")
    list_filter = ("type", "warehouse")
    search_fields = (
        "product__name",
        "receipt__supplier__company_name",
        "sale__customer__first_name",
        "sale__customer__last_name",
    )
    date_hierarchy = "date"
    readonly_fields = ("date",)

    @admin.display(description="Контрагент")
    def get_counterparty(self, obj):
        if obj.type == "IN" and obj.receipt and obj.receipt.supplier:
            return obj.receipt.supplier.company_name
        elif obj.type == "OUT" and obj.sale and obj.sale.customer:
            return f"{obj.sale.customer.first_name} {obj.sale.customer.last_name}"
        return "-"
