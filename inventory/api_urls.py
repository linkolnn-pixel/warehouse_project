from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet,
    WarehouseViewSet,
    ReceiptViewSet,
    SaleViewSet,
)


router = DefaultRouter()

router.register(
    r'products',
    ProductViewSet,
    basename='product'
)

router.register(
    r'warehouses',
    WarehouseViewSet,
    basename='warehouse'
)

router.register(
    r'receipts',
    ReceiptViewSet,
    basename='receipt'
)

router.register(
    r'sales',
    SaleViewSet,
    basename='sale'
)

urlpatterns = router.urls