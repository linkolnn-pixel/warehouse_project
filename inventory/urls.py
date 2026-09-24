from django.urls import path
from rest_framework.routers import DefaultRouter

from .views.analytics import dashboard_view
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
    api_counterparty_create,
    counterparty_create,
    customer_create,
    customer_detail,
    customers_list,
)
from .views.stock import movement_report, stock_management_view

router = DefaultRouter()

router.register(r"products", ProductViewSet, basename="product")

urlpatterns = [
    # Главная = склад
    path("", stock_management_view, name="home"),
    # Каталог товаров
    path("catalog/", products_catalog_view, name="products_catalog"),
    # Склад
    path("stock/", stock_management_view, name="stock_management"),
    # Создание товара
    path("product/new/", create_product, name="create_product"),
    # Импорт Excel (разовый)
    path("products/upload/", upload_products, name="upload_products"),
    # Карточка товара
    path("product/<int:pk>/", product_detail, name="product_detail"),
    # Редактирование товара
    path("product/<int:pk>/edit/", product_edit, name="product_edit"),
    # Создание поставщика
    path("counterparty/new/", counterparty_create, name="counterparty_create"),
    path(
        "api/counterparty/create/",
        api_counterparty_create,
        name="api_counterparty_create",
    ),
    # Создание категории
    path("category/new/", category_create, name="category_create"),
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
    # Пикер товаров
    path("products/picker/", product_picker, name="product_picker"),
    # Клиенты
    path("customers/create/", customer_create, name="customer_create"),
    path("customers/", customers_list, name="customers_list"),
    path("customers/<int:pk>/", customer_detail, name="customer_detail"),
    # Операции
    path("report/", movement_report, name="movement_report"),
    # Аналитика
    path("dashboard/", dashboard_view, name="dashboard"),
]

urlpatterns += router.urls
