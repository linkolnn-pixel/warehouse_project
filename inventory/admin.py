from django import forms
from django.contrib import admin, messages
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.shortcuts import render
from mptt.admin import DraggableMPTTAdmin

from .models import (
    Category,
    Customer,
    GiftCertificate,
    Product,
    PromoCode,
    Sale,
    SaleItem,
    StockBalance,
    Supplier,
    Transaction,
    Warehouse,
)
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
class CategoryAdmin(DraggableMPTTAdmin):
    mptt_indent_field = "name"
    list_display = ("tree_actions", "indented_title", "slug")
    list_display_links = ("indented_title",)
    prepopulated_fields = {"slug": ("name",)}


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
    list_display = (
        "number",
        "customer",
        "warehouse",
        "is_online",
        "get_subtotal",
        "get_discount_info",
        "get_total",
        "get_profit",
        "posted",
        "date",
    )
    list_filter = ("posted", "is_online", "warehouse", "date", "promo_code")
    search_fields = ("customer__phone", "customer__last_name", "comment", "promo_code__code", "gift_certificate__code")
    autocomplete_fields = ["customer"]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_online:
            # Блокируем и промокоды, и подарочные сертификаты для сайтовых заказов
            return ("promo_code", "discount_amount", "gift_certificate", "certificate_amount_used")
        return ()

    @admin.display(description="Сумма товаров")
    def get_subtotal(self, obj):
        subtotal = sum(item.total for item in obj.items.all())
        return f"{subtotal} руб."

    @admin.display(description="Промокод / Скидка")
    def get_discount_info(self, obj):
        if obj.discount_amount and obj.discount_amount > 0:
            code = obj.promo_code.code if obj.promo_code else "Ручная скидка"
            return f"{code} (-{obj.discount_amount} руб.)"
        return "-"

    @admin.display(description="К оплате")
    def get_total(self, obj):
        return f"{obj.calculated_total} руб."

    @admin.display(description="Прибыль")
    def get_profit(self, obj):
        prefix = "" if obj.posted else "~ "
        return f"{prefix}{obj.net_profit} руб."


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "discount_value", "get_status", "used_count", "usage_limit", "valid_to")
    list_filter = ("is_active", "discount_type", "is_deleted")
    search_fields = ("code",)
    readonly_fields = ("used_count",)

    fieldsets = (
        ("Основная информация", {"fields": ("code", "is_active", "is_deleted")}),
        ("Настройки скидки", {"fields": ("discount_type", "discount_value", "min_order_amount")}),
        ("Ограничения", {"fields": ("valid_from", "valid_to", "usage_limit", "used_count")}),
    )

    @admin.display(description="Статус")
    def get_status(self, obj):
        if obj.is_deleted:
            return "Удален"
        if not obj.is_active:
            return "Выключен"
        if not obj.is_valid_now:
            return "Истек / Исчерпан"
        return "Активен"


# ====================================================
# ПОДАРОЧНЫЕ СЕРТИФИКАТЫ И ГЕНЕРАТОР
# ====================================================


class GenerateCertificatesForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    count = forms.IntegerField(label="Количество сертификатов", min_value=1, max_value=500, initial=50)
    nominal = forms.DecimalField(label="Номинал (руб.)", min_value=100, max_value=100000, initial=5000)
    prefix = forms.CharField(label="Префикс (необязательно)", max_length=10, initial="MDM-", required=False)  # type: ignore[assignment]


@admin.register(GiftCertificate)
class GiftCertificateAdmin(admin.ModelAdmin):
    list_display = ("code", "initial_balance", "current_balance", "is_active", "created_at")
    list_filter = ("is_active", "created_at", "initial_balance")
    search_fields = ("code",)
    readonly_fields = ("created_at",)

    actions = ["generate_multiple_certificates"]

    @admin.action(description="Сгенерировать новые сертификаты")
    def generate_multiple_certificates(self, request, queryset):
        from django.contrib.admin import helpers

        if "apply" in request.POST:
            form = GenerateCertificatesForm(request.POST)
            if form.is_valid():
                count = form.cleaned_data["count"]
                nominal = form.cleaned_data["nominal"]
                prefix = form.cleaned_data["prefix"]

                new_certs = []
                for _ in range(count):
                    new_code = GiftCertificate.generate_code(prefix=prefix)
                    new_certs.append(
                        GiftCertificate(code=new_code, initial_balance=nominal, current_balance=nominal, is_active=True)
                    )

                GiftCertificate.objects.bulk_create(new_certs)

                self.message_user(
                    request,
                    f"Успешно сгенерировано {count} сертификатов номиналом {nominal} руб.",
                    level=messages.SUCCESS,
                )
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = GenerateCertificatesForm(
                initial={"_selected_action": request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)}
            )

        return render(
            request,
            "admin/generate_certificates.html",
            {
                "items": queryset,
                "form": form,
                "title": "Генерация подарочных сертификатов",
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            },
        )
