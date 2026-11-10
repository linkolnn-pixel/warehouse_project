from django.contrib import admin, messages
from django.db.models import Sum

from .models import Category, Customer, Product, Sale, SaleItem, StockBalance, Supplier, Transaction, Warehouse
from .services import process_sale_post, process_sale_unpost


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
    list_display = ("first_name", "last_name", "phone", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("first_name", "last_name", "phone")

    class Media:
        js = (
            "https://unpkg.com/imask",
            "inventory/js/admin_phone.js",
        )


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
    list_select_related = ("product", "warehouse", "receipt__supplier", "sale__customer")
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


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    autocomplete_fields = ["product"]


@admin.action(description="Провести выбранные заказы (списать товар)")
def admin_post_sales(modeladmin, request, queryset):
    success_count = 0
    error_count = 0

    for sale in queryset:
        if sale.posted:
            continue

        try:
            process_sale_post(sale)
            success_count += 1
        except Exception as e:
            modeladmin.message_user(request, f"Ошибка проведения заказа #{sale.number}: {e}", level=messages.ERROR)
            error_count += 1

    if success_count > 0:
        modeladmin.message_user(request, f"Успешно проведено заказов: {success_count}", level=messages.SUCCESS)


@admin.action(description="Отменить проведение (вернуть товары)")
def admin_unpost_sales(modeladmin, request, queryset):
    success_count = 0
    for sale in queryset:
        if not sale.posted:
            continue

        try:
            process_sale_unpost(sale)
            success_count += 1
        except Exception as e:
            modeladmin.message_user(request, f"Ошибка отмены заказа #{sale.number}: {e}", level=messages.ERROR)

    if success_count > 0:
        modeladmin.message_user(
            request, f"Успешно отменено проведение для {success_count} заказов.", level=messages.SUCCESS
        )


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    actions = [admin_post_sales, admin_unpost_sales]
    inlines = [SaleItemInline]

    # Выводим is_online (Заказ с сайта), чтобы сразу видеть источник
    list_display = ("number", "customer", "warehouse", "is_online", "get_total", "get_profit", "posted", "date")
    list_filter = ("posted", "is_online", "warehouse", "date")
    search_fields = ("customer__phone", "customer__last_name", "comment")
    autocomplete_fields = ["customer"]

    @admin.display(description="Сумма")
    def get_total(self, obj):
        return f"{obj.calculated_total} руб."

    @admin.display(description="Прибыль")
    def get_profit(self, obj):
        prefix = "" if obj.posted else "~ "
        return f"{prefix}{obj.net_profit} руб."
