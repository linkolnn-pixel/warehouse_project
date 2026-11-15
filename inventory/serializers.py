import re

from django.db import transaction
from rest_framework import serializers

from .models import (
    Category,
    Customer,
    GiftCertificate,
    Product,
    PromoCode,
    Receipt,
    ReceiptItem,
    Sale,
    SaleItem,
    Warehouse,
)


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    supplier_name = serializers.CharField(source="supplier.company_name", read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "internal_code",
            "sku",
            "brand",
            "name",
            "category",
            "category_name",
            "unit",
            "cost_price",
            "sale_price",
            "quantity_value",
            "measure_unit",
            "supplier",
            "supplier_name",
            "average_cost",
            "consumption_time",
        ]
        read_only_fields = ["internal_code"]  # Внутренний код генерируется автоматически


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            "id",
            "name",
            "address",
        ]


class WarehouseStockSerializer(serializers.ModelSerializer):
    balance = serializers.IntegerField(read_only=True)
    profit_per_unit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    stock_profit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    product_id = serializers.IntegerField(source="id", read_only=True)
    product_name = serializers.CharField(source="name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    supplier_name = serializers.CharField(source="supplier.company_name", read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "product_id",
            "product_name",
            "brand",
            "category_name",
            "internal_code",
            "sku",
            "supplier_name",
            "unit",
            "cost_price",
            "sale_price",
            "balance",
            "profit_per_unit",
            "stock_profit",
        ]


class ReceiptItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_sale = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ReceiptItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "cost_price",
            "sale_price",
            "total_cost",
            "total_sale",
        ]


class ReceiptSerializer(serializers.ModelSerializer):
    items = ReceiptItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.company_name", read_only=True, allow_null=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "number",
            "date",
            "warehouse",
            "warehouse_name",
            "supplier",
            "supplier_name",
            "delivery_cost",
            "comment",
            "posted",
            "items",
        ]
        read_only_fields = [
            "id",
            "number",
            "date",
            "posted",
        ]

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        receipt = Receipt.objects.create(**validated_data)

        if items_data:
            ReceiptItem.objects.bulk_create([ReceiptItem(receipt=receipt, **item_data) for item_data in items_data])
        return receipt


class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = SaleItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "sale_price",
            "total",
        ]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    customer_name = serializers.SerializerMethodField()
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    promo_code = serializers.SlugRelatedField(
        slug_field="code", queryset=PromoCode.objects.all(), allow_null=True, required=False
    )
    calculated_total = serializers.SerializerMethodField()
    gift_certificate = serializers.SlugRelatedField(
        slug_field="code", queryset=GiftCertificate.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Sale
        fields = [
            "id",
            "number",
            "date",
            "warehouse",
            "warehouse_name",
            "customer",
            "customer_name",
            "delivery_expense",
            "comment",
            "is_online",
            "external_id",
            "posted",
            "items",
            "promo_code",
            "discount_amount",
            "calculated_total",
            "gift_certificate",
            "certificate_amount_used",
        ]
        read_only_fields = [
            "id",
            "number",
            "date",
            "posted",
        ]

    def get_customer_name(self, obj):
        if not obj.customer:
            return None
        return f"{obj.customer.last_name} {obj.customer.first_name}".strip()

    def get_calculated_total(self, obj):
        # Считаем сумму всех товаров в чеке
        items_sum = sum(item.sale_price * item.quantity for item in obj.items.all())
        # Вычитаем скидку по промокоду (если она есть)
        discount = obj.discount_amount or 0
        # Возвращаем итоговую сумму к оплате
        return items_sum - discount

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")
        gift_certificate = validated_data.get("gift_certificate")
        sale = Sale.objects.create(**validated_data)

        sale_items = []
        total_items_sum = 0
        for item_data in items_data:
            product = item_data["product"]
            cost_price = product.average_cost if product.average_cost > 0 else product.cost_price
            sale_price = item_data["sale_price"]
            quantity = item_data["quantity"]

            total_items_sum += sale_price * quantity

            sale_items.append(SaleItem(sale=sale, cost_price=cost_price, **item_data))
        SaleItem.objects.bulk_create(sale_items)

        # ==========================================
        # ЛОГИКА ОПЛАТЫ ПОДАРОЧНЫМ СЕРТИФИКАТОМ
        # ==========================================
        final_total_to_pay = total_items_sum - (sale.discount_amount or 0)

        final_total_to_pay = total_items_sum - (sale.discount_amount or 0)

        if gift_certificate:
            # ПЕРЕЗАПРАШИВАЕМ СЕРТИФИКАТ С БЛОКИРОВКОЙ!
            # Это гарантирует, что параллельные запросы встанут в очередь.
            locked_cert = GiftCertificate.objects.select_for_update().get(id=gift_certificate.id)

            if locked_cert.is_active and locked_cert.current_balance > 0:
                amount_to_deduct = min(final_total_to_pay, locked_cert.current_balance)

                if amount_to_deduct > 0:
                    sale.certificate_amount_used = amount_to_deduct
                    sale.save(update_fields=["certificate_amount_used"])

                    locked_cert.current_balance -= amount_to_deduct
                    if locked_cert.current_balance <= 0:
                        locked_cert.is_active = False
                    locked_cert.save(update_fields=["current_balance", "is_active"])
            else:
                # Если во время блокировки выяснилось, что деньги уже списал другой запрос
                raise serializers.ValidationError({"gift_certificate": "Сертификат уже исчерпан или неактивен."})

        return sale


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "first_name", "last_name", "phone"]
        read_only_fields = ["id"]

    def validate_phone(self, value):
        if not value:
            return value

        cleaned = re.sub(r"[^\d+]", "", value)

        if cleaned.startswith("8") and len(cleaned) == 11:
            cleaned = "+7" + cleaned[1:]

        elif cleaned.startswith("9") and len(cleaned) == 10:
            cleaned = "+7" + cleaned

        elif cleaned.startswith("7") and len(cleaned) == 11:
            cleaned = "+" + cleaned

        if not re.match(r"^\+7\d{10}$", cleaned):
            raise serializers.ValidationError("Введите телефон в формате +79999999999")

        return cleaned
