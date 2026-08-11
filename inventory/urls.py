from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet


router = DefaultRouter()

router.register(
    r'products',
    ProductViewSet,
    basename='product'
)

urlpatterns = [

    # Главная = склад
    path('', views.stock_management_view, name='home'),


    # Каталог товаров
    path('catalog/', views.products_catalog_view, name='products_catalog'),


    # Склад
    path('stock/', views.stock_management_view, name='stock_management'),


    # Создание товара
    path(
        'product/new/',
        views.create_product,
        name='create_product'
    ),


    # Импорт Excel (разовый)
    path(
        'products/upload/',
        views.upload_products,
        name='upload_products'
    ),


    # Карточка товара
    path(
        'product/<int:pk>/',
        views.product_detail,
        name='product_detail'
    ),


    # Редактирование товара
    path(
        'product/<int:pk>/edit/',
        views.product_edit,
        name='product_edit'
    ),


    # Создание поставщика
    path(
        'counterparty/new/',
        views.counterparty_create,
        name='counterparty_create'
    ),


    # Создание категории
    path(
        'category/new/',
        views.category_create,
        name='category_create'
    ),


    # Приход
    path(
        'receipt/create/',
        views.receipt_create,
        name='receipt_create'
    ),

    path(
        'receipt/<int:pk>/',
        views.receipt_detail,
        name='receipt_detail'
    ),

    path(
        'receipt/<int:pk>/post/',
        views.receipt_post,
        name='receipt_post'
    ),

    # Продажа
    path(
        'sale/create/',
        views.sale_create,
        name='sale_create'
    ),

    path(
        'sale/<int:pk>/',
        views.sale_detail,
        name='sale_detail'
    ),

    path(
        'sale/<int:pk>/post/',
        views.sale_post,
        name='sale_post'
    ),

    path(
        "customers/create/",
        views.customer_create,
        name="customer_create",
    ),


    path(
        'products/picker/',
        views.product_picker,
        name='product_picker'
    ),

    # Клиенты

    path(
        'customers/',
        views.customers_list,
        name='customers_list'
    ),

    path(
        'customers/<int:pk>/',
        views.customer_detail,
        name='customer_detail'
    ),

    # Операции
    path(
        'report/',
        views.movement_report,
        name='movement_report'
    ),

]

urlpatterns += router.urls