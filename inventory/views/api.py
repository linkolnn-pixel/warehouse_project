from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from inventory.exceptions import InventoryError
from inventory.models import Category, Customer, Product, Receipt, Sale, Warehouse
from inventory.permissions import TestModeOrAuthenticated
from inventory.serializers import (
    CategorySerializer,
    CustomerSerializer,
    ProductSerializer,
    ReceiptSerializer,
    SaleSerializer,
    WarehouseSerializer,
    WarehouseStockSerializer,
)
from inventory.services import process_receipt_post, process_sale_post


class ProductViewSet(ReadOnlyModelViewSet):
    permission_classes = [TestModeOrAuthenticated]
    queryset = Product.objects.select_related(
        "category",
        "supplier",
    ).all()
    serializer_class = ProductSerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class WarehouseViewSet(ReadOnlyModelViewSet):
    permission_classes = [TestModeOrAuthenticated]
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer

    @action(detail=True, methods=["get"], url_path="stock")
    def stock(self, request, pk=None):
        warehouse = self.get_object()

        products = Product.objects.with_balances(warehouse.id).select_related("category", "supplier").all()

        search = request.query_params.get("q")

        if search:
            products = products.filter(
                Q(name__icontains=search) | Q(sku__icontains=search) | Q(internal_code__icontains=search)
            )

        category_id = request.query_params.get("category")

        if category_id:
            products = products.filter(category_id=category_id)

        supplier_id = request.query_params.get("supplier")

        if supplier_id:
            products = products.filter(supplier_id=supplier_id)

        serializer = WarehouseStockSerializer(
            products,
            many=True,
            context={
                "request": request,
                "warehouse": warehouse,
            },
        )

        return Response(serializer.data)


class ReceiptViewSet(ModelViewSet):
    permission_classes = [TestModeOrAuthenticated]
    queryset = (
        Receipt.objects.select_related(
            "warehouse",
            "supplier",
        )
        .prefetch_related("items__product")
        .all()
    )

    serializer_class = ReceiptSerializer

    @action(detail=True, methods=["post"], url_path="post")
    def post_receipt(self, request, pk=None):
        receipt = self.get_object()

        try:
            process_receipt_post(receipt)

        except InventoryError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            ReceiptSerializer(receipt, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class SaleViewSet(ModelViewSet):
    permission_classes = [TestModeOrAuthenticated]
    queryset = (
        Sale.objects.select_related(
            "warehouse",
            "customer",
        )
        .prefetch_related("items__product")
        .all()
    )

    serializer_class = SaleSerializer

    @action(detail=True, methods=["post"], url_path="post")
    def post_sale(self, request, pk=None):
        sale = self.get_object()

        try:
            process_sale_post(sale)

        except InventoryError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            SaleSerializer(sale, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class CustomerViewSet(ModelViewSet):
    permission_classes = [TestModeOrAuthenticated]
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Позволяем воркеру искать клиента по номеру телефона
        phone = self.request.query_params.get("phone")
        if phone:
            phone = phone.replace(" ", "+").strip()
            # На случай, если плюса вообще нет, но он должен быть
            if not phone.startswith("+"):
                phone = f"+{phone}"
            queryset = queryset.filter(phone=phone)
        return queryset

    def create(self, request, *args, **kwargs):
        print("REQUEST DATA:", request.data)

        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            print("VALIDATION ERRORS:", serializer.errors)
            return Response(serializer.errors, status=400)

        try:
            self.perform_create(serializer)
        except Exception as e:
            print("SAVE ERROR:", repr(e))
            raise

        return Response(serializer.data, status=201)
