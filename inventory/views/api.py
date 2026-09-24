from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet, ModelViewSet

from inventory.exceptions import InventoryError
from inventory.models import Product, Warehouse, Receipt, Sale
from inventory.permissions import TestModeOrAuthenticated
from inventory.serializers import (
    ProductSerializer,
    WarehouseSerializer,
    WarehouseStockSerializer,
    ReceiptSerializer,
    SaleSerializer
)
from inventory.services import post_sale_document, post_receipt_document


class ProductViewSet(ReadOnlyModelViewSet):
    permission_classes = [TestModeOrAuthenticated]
    queryset = Product.objects.select_related(
        'category',
        'supplier',
    ).all()
    serializer_class = ProductSerializer

class WarehouseViewSet(ReadOnlyModelViewSet):
    permission_classes = [TestModeOrAuthenticated]
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer

    @action(
        detail=True,
        methods=['get'],
        url_path='stock'
    )
    def stock(self, request, pk=None):
        warehouse = self.get_object()

        products = Product.objects.with_balances(warehouse.id).select_related(
            'category',
            'supplier'
        ).all()

        search = request.query_params.get('q')

        if search:
            products = products.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search) |
                Q(internal_code__icontains=search)
            )

        category_id = request.query_params.get('category')

        if category_id:
            products = products.filter(
                category_id=category_id
            )

        supplier_id = request.query_params.get('supplier')

        if supplier_id:
            products = products.filter(
                supplier_id=supplier_id
            )

        serializer = WarehouseStockSerializer(
            products,
            many=True,
            context={
                'request': request,
                'warehouse': warehouse,
            }
        )

        return Response(serializer.data)

class ReceiptViewSet(ModelViewSet):
    permission_classes = [TestModeOrAuthenticated]
    queryset = Receipt.objects.select_related(
        'warehouse',
        'supplier',
    ).prefetch_related(
        'items__product'
    ).all()

    serializer_class = ReceiptSerializer

    @action(
        detail=True,
        methods=['post'],
        url_path='post'
    )
    def post_receipt(self, request, pk=None):
        receipt = self.get_object()

        try:
            post_receipt_document(receipt)

        except InventoryError as e:
            return Response(
                {
                    'detail': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            ReceiptSerializer(
                receipt,
                context={'request': request}
            ).data,
            status=status.HTTP_200_OK
        )

class SaleViewSet(ModelViewSet):
    permission_classes = [TestModeOrAuthenticated]
    queryset = Sale.objects.select_related(
        'warehouse',
        'customer',
    ).prefetch_related(
        'items__product'
    ).all()

    serializer_class = SaleSerializer

    @action(
        detail=True,
        methods=['post'],
        url_path='post'
    )
    @action(detail=True, methods=['post'], url_path='post')
    def post_sale(self, request, pk=None):
        sale = self.get_object()

        try:
            post_sale_document(sale)

        except InventoryError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            SaleSerializer(sale, context={'request': request}).data,
            status=status.HTTP_200_OK
        )