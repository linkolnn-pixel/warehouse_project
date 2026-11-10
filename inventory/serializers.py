import re

from django.db import transaction
from rest_framework import serializers

from .models import (
    Category,
    Customer,
    Product,
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
            "posted",
            "items",
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

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")
        sale = Sale.objects.create(**validated_data)

        SaleItem.objects.bulk_create([SaleItem(sale=sale, **item_data) for item_data in items_data])
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
