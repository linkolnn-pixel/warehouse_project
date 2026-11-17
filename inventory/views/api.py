from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from inventory.exceptions import InventoryError
from inventory.models import Category, Customer, GiftCertificate, Product, PromoCode, Receipt, Sale, Warehouse
from inventory.permissions import IsServiceOrAuthenticated
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
    permission_classes = [IsServiceOrAuthenticated]
    queryset = Product.objects.select_related(
        "category",
        "supplier",
    ).all()
    serializer_class = ProductSerializer

    @action(detail=False, methods=["get"], url_path="new_arrivals")
    def new_arrivals(self, request):
        # Отсчитываем 60 дней назад от сегодняшнего дня
        two_months_ago = timezone.now() - timedelta(days=60)

        # Фильтруем товары (исключаем те, у которых created_at=None)
        recent_products = (
            self.get_queryset().filter(created_at__isnull=False, created_at__gte=two_months_ago).order_by("-created_at")
        )

        serializer = self.get_serializer(recent_products, many=True)
        return Response(serializer.data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class WarehouseViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsServiceOrAuthenticated]
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
    permission_classes = [IsServiceOrAuthenticated]
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
    permission_classes = [IsServiceOrAuthenticated]
    serializer_class = SaleSerializer

    def get_queryset(self):
        queryset = Sale.objects.select_related("warehouse", "customer").prefetch_related("items__product").all()

        external_id = self.request.query_params.get("external_id")
        if external_id:
            queryset = queryset.filter(external_id=external_id)

        phone = self.request.query_params.get("phone")
        if phone:
            phone = phone.replace(" ", "+").strip()
            if not phone.startswith("+"):
                phone = f"+{phone}"
            queryset = queryset.filter(customer__phone=phone)

        return queryset

    # ========================================================
    # НОВЫЙ МЕТОД: Перехватываем создание продажи!
    # ========================================================
    def create(self, request, *args, **kwargs):
        import copy

        # Копируем данные, так как request.data может быть неизменяемым
        data = copy.deepcopy(request.data)
        raw_items = data.get("items", [])

        physical_items = []
        certificate_items = []

        # 1. Сортируем: физические товары — налево, сертификаты — направо
        for item in raw_items:
            if str(item.get("product_id", "")).startswith("CERT_"):
                certificate_items.append(item)
            else:
                physical_items.append(item)

        # 2. Отдаем сериализатору ТОЛЬКО физические товары, чтобы он не ругался
        data["items"] = physical_items

        # 3. Сохраняем обычную продажу (даже если список items пуст, мы зафиксируем доход)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # 4. ГЕНЕРИРУЕМ НАСТОЯЩИЕ СЕРТИФИКАТЫ
        generated_certs = []
        for cert_item in certificate_items:
            amount = cert_item.get("price")
            # Создаем реальную запись в БД через твою модель
            new_code = GiftCertificate.generate_code(prefix="MDM-")
            GiftCertificate.objects.create(
                code=new_code, initial_balance=amount, current_balance=amount, is_active=True
            )
            # Собираем данные, чтобы вернуть их воркеру
            generated_certs.append(
                {
                    "code": new_code,
                    "amount": str(amount),
                    "name": cert_item.get("name", f"Подарочный сертификат на {amount} ₽"),
                }
            )

        # 5. Формируем финальный ответ, подмешивая туда свежие промокоды
        response_data = serializer.data
        response_data["generated_certificates"] = generated_certs

        headers = self.get_success_headers(serializer.data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

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
    permission_classes = [IsServiceOrAuthenticated]
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


@api_view(["GET"])
@permission_classes([IsServiceOrAuthenticated])
def validate_promo_code_api(request):
    """
    Эндпоинт для проверки валидности промокода.
    Использование: GET /api/promocodes/validate/?code=NEWYEAR27
    """
    code = request.GET.get("code", "").strip()

    if not code:
        return Response({"is_valid": False, "message": "Промокод не указан."}, status=400)

    # Ищем промокод (iexact делает поиск независимым от регистра: newyear == NEWYEAR)
    promo = PromoCode.objects.filter(code__iexact=code).first()

    if not promo:
        return Response({"is_valid": False, "message": "Такого промокода не существует."}, status=404)

    # Используем наше свойство is_valid_now из модели
    if not promo.is_valid_now:
        return Response(
            {"is_valid": False, "message": "Срок действия промокода истек или исчерпан лимит использований."},
            status=400,
        )

    # Если всё отлично, отдаем параметры скидки
    return Response(
        {
            "is_valid": True,
            "code": promo.code,
            "discount_type": promo.discount_type,
            "discount_value": str(promo.discount_value),  # Переводим в строку для точности Decimal
            "min_order_amount": str(promo.min_order_amount),
        },
        status=200,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def validate_certificate_api(request):
    code = request.GET.get("code")
    if not code:
        return Response({"is_valid": False, "message": "Код не передан"}, status=400)

    try:
        # Ищем сертификат (без учета регистра)
        cert = GiftCertificate.objects.get(code__iexact=code.strip())

        if not cert.is_active or cert.current_balance <= 0:
            return Response({"is_valid": False, "message": "Сертификат исчерпан или неактивен"}, status=400)

        return Response({"is_valid": True, "current_balance": cert.current_balance})
    except GiftCertificate.DoesNotExist:
        return Response({"is_valid": False, "message": "Сертификат не найден"}, status=404)


@api_view(["POST"])
@permission_classes([IsServiceOrAuthenticated])
def create_certificate_api(request):
    """
    Эндпоинт для FastAPI: создает 1 сертификат при онлайн-покупке
    """
    # DRF сам парсит JSON, так что request.body и json.loads больше не нужны
    amount = request.data.get("amount")

    if not amount:
        return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        new_code = GiftCertificate.generate_code(prefix="MDM-")

        cert = GiftCertificate.objects.create(
            code=new_code, initial_balance=amount, current_balance=amount, is_active=True
        )

        return Response(
            {"status": "success", "code": cert.code, "balance": str(cert.initial_balance)},
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
