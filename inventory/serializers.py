from django.db import transaction
from rest_framework import serializers

from .models import (
    Product,
    Receipt,
    ReceiptItem,
    Warehouse,
    Counterparty,
    Sale,
    SaleItem
)


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name',
        read_only=True,
        allow_null=True
    )

    supplier_name = serializers.CharField(
        source='supplier.company_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Product
        fields = [
            'id',
            'internal_code',
            'sku',
            'name',
            'category',
            'category_name',
            'unit',
            'cost_price',
            'sale_price',
            'quantity_value',
            'measure_unit',
            'supplier',
            'supplier_name',
        ]

class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            'id',
            'name',
            'address',
        ]

class WarehouseStockSerializer(serializers.ModelSerializer):
    balance = serializers.IntegerField(read_only=True)
    profit = serializers.DecimalField(max_digits=12, decimal_places=2,read_only=True)
    stock_profit = serializers.DecimalField(max_digits=12, decimal_places=2,read_only=True)

    product_id = serializers.IntegerField(source='id', read_only=True)
    product_name = serializers.CharField(source='name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    supplier_name = serializers.CharField(source='supplier.company_name', read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            'product_id',
            'product_name',
            'category_name',
            'internal_code',
            'sku',
            'supplier_name',
            'unit',
            'cost_price',
            'sale_price',
            'balance',
            'profit',
            'stock_profit',
        ]

class ReceiptItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source='product.name',
        read_only=True
    )

    total_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )

    total_sale = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = ReceiptItem
        fields = [
            'id',
            'product',
            'product_name',
            'quantity',
            'cost_price',
            'sale_price',
            'total_cost',
            'total_sale',
        ]


class ReceiptSerializer(serializers.ModelSerializer):
    items = ReceiptItemSerializer(many=True)
    supplier_name = serializers.CharField(source='supplier.company_name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = Receipt
        fields = [
            'id',
            'number',
            'date',
            'warehouse',
            'warehouse_name',
            'supplier',
            'supplier_name',
            'comment',
            'posted',
            'items',
        ]
        read_only_fields = [
            'id',
            'number',
            'date',
            'posted',
        ]

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        receipt = Receipt.objects.create(**validated_data)

        if items_data:
            ReceiptItem.objects.bulk_create([
                ReceiptItem(receipt=receipt, **item_data)
                for item_data in items_data
            ])
        return receipt

class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source='product.name',
        read_only=True
    )

    total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = SaleItem
        fields = [
            'id',
            'product',
            'product_name',
            'quantity',
            'sale_price',
            'total',
        ]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True, allow_null=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = Sale
        fields = [
            'id',
            'number',
            'date',
            'warehouse',
            'warehouse_name',
            'customer',
            'customer_name',
            'comment',
            'posted',
            'items',
        ]

        read_only_fields = [
            'id',
            'number',
            'date',
            'posted',
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items')

        sale = Sale.objects.create(**validated_data)

        SaleItem.objects.bulk_create([
            SaleItem(sale=sale, **item_data)
            for item_data in items_data
        ])
        return sale

