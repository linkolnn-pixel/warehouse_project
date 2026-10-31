from django.urls import path
from rest_framework.routers import DefaultRouter

from .views.analysis import analysis_view
from .views.analytics import abc_analysis_view, dashboard_view
from .views.api import ProductViewSet
from .views.catalog import (
    category_create,
    create_product,
    product_detail,
    product_edit,
    product_picker,
    products_catalog_view,
    upload_products,
)
from .views.documents import (
    receipt_create,
    receipt_detail,
    receipt_edit,
    receipt_post,
    receipt_unpost,
    sale_create,
    sale_detail,
    sale_edit,
    sale_post,
    sale_unpost,
)
from .views.partners import (
    api_customer_create,
    api_supplier_create,
    customer_create,
    customer_detail,
    customers_list,
    supplier_create,
)
from .views.stock import movement_report, stock_management_view

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")

urlpatterns = [
    # Главная = склад
    path("", stock_management_view, name="home"),
    # Каталог товаров
    path("catalog/", products_catalog_view, name="products_catalog"),
    path("stock/", stock_management_view, name="stock_management"),
    path("product/new/", create_product, name="create_product"),
    path("products/upload/", upload_products, name="upload_products"),
    path("product/<int:pk>/", product_detail, name="product_detail"),
    path("product/<int:pk>/edit/", product_edit, name="product_edit"),
    path("products/picker/", product_picker, name="product_picker"),
    path("category/new/", category_create, name="category_create"),
    # ПОСТАВЩИКИ
    path("supplier/new/", supplier_create, name="supplier_create"),
    path("api/supplier/create/", api_supplier_create, name="api_supplier_create"),
    # КЛИЕНТЫ
    path("customers/create/", customer_create, name="customer_create"),
    path("customers/", customers_list, name="customers_list"),
    path("customers/<int:pk>/", customer_detail, name="customer_detail"),
    path("api/customer/create/", api_customer_create, name="api_customer_create"),
    # Приход
    path("receipt/create/", receipt_create, name="receipt_create"),
    path("receipt/<int:pk>/", receipt_detail, name="receipt_detail"),
    path("receipt/<int:pk>/post/", receipt_post, name="receipt_post"),
    path("receipt/<int:pk>/unpost/", receipt_unpost, name="receipt_unpost"),
    path("receipt/<int:pk>/edit/", receipt_edit, name="receipt_edit"),
    # Продажа
    path("sale/create/", sale_create, name="sale_create"),
    path("sale/<int:pk>/", sale_detail, name="sale_detail"),
    path("sale/<int:pk>/post/", sale_post, name="sale_post"),
    path("sale/<int:pk>/unpost/", sale_unpost, name="sale_unpost"),
    path("sale/<int:pk>/edit/", sale_edit, name="sale_edit"),
    # Операции и Аналитика
    path("report/", movement_report, name="movement_report"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("abc-analysis/", abc_analysis_view, name="abc_analysis"),
    path("analysis/", analysis_view, name="analysis"),
]

urlpatterns += router.urls
