from rest_framework.routers import DefaultRouter

from inventory.views.api import (
    ProductViewSet,
    ReceiptViewSet,
    SaleViewSet,
    WarehouseViewSet,
)

router = DefaultRouter()

router.register(r"products", ProductViewSet, basename="product")

router.register(r"warehouses", WarehouseViewSet, basename="warehouse")

router.register(r"receipts", ReceiptViewSet, basename="receipt")

router.register(r"sales", SaleViewSet, basename="sale")

urlpatterns = router.urls
