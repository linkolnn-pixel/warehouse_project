from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from rest_framework.generics import get_object_or_404

from ..decorators import test_mode_login_required
from ..exceptions import ExcelImportError
from ..forms import CategoryForm, ProductEditForm, ProductForm
from ..models import Category, Product, Transaction, Warehouse
from ..services import import_products_from_excel


@test_mode_login_required
def products_catalog_view(request):
    brands = Category.objects.filter(parent__isnull=True).order_by("name")

    products = Product.objects.select_related("category", "supplier").order_by("brand", "name")

    # Фильтр по бренду/категории
    selected_cat_id = request.GET.get("cat")
    selected_category = None

    if selected_cat_id:
        selected_category = get_object_or_404(Category, id=selected_cat_id)

        products = products.filter(category=selected_category)

    # Поиск
    query = request.GET.get("q", "").strip()

    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(sku__icontains=query) | Q(internal_code__icontains=query)
        )

    context = {
        "products": products,
        "brands": brands,
        "selected_category": selected_category,
        "page_title": "Каталог товаров",
        "query": query,
    }

    return render(request, "inventory/catalog_page.html", context)


@test_mode_login_required
def product_detail(request, pk):
    warehouse = Warehouse.objects.first()
    warehouse_id = warehouse.id if warehouse else None

    product = get_object_or_404(
        Product.objects.with_balances(warehouse_id).select_related("category", "supplier"),
        pk=pk,
    )
    # getattr нужен на случай, если склада нет
    balance = getattr(product, "balance", 0)
    stock_profit = getattr(product, "stock_profit", 0)

    transactions = (
        Transaction.objects.filter(product=product).select_related("warehouse", "counterparty").order_by("-date")
    )

    return render(
        request,
        "inventory/product_detail.html",
        {
            "product": product,
            "transactions": transactions,
            "warehouse": warehouse,
            "balance": balance,
            "stock_profit": stock_profit,
        },
    )


@test_mode_login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductEditForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Товар успешно обновлен")
            return redirect("product_detail", pk=product.pk)
    else:
        form = ProductEditForm(instance=product)
    return render(request, "inventory/product_edit.html", {"form": form, "product": product})


@test_mode_login_required
def create_product(request):
    next_name = request.GET.get("next", "products_catalog")
    target = request.GET.get("target", "")
    selected_products = request.GET.getlist("products")
    customer_id = request.GET.get("customer")
    supplier_id = request.GET.get("supplier")
    category_id = request.GET.get("category")

    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.save()
            messages.success(request, "Товар успешно создан!")
            # Если пришли из выбора товаров
            if next_name == "product_picker":
                params = [
                    f"target={target}",
                    f"products={product.pk}",
                ]
                # Старые товары
                for product_id in selected_products:
                    if product_id != str(product.pk):
                        params.append(f"products={product_id}")
                # Клиент
                if customer_id and customer_id.isdigit():
                    params.append(f"customer={customer_id}")
                # Поставщик
                if supplier_id and supplier_id.isdigit():
                    params.append(f"supplier={supplier_id}")
                return redirect(f"{reverse('product_picker')}?" + "&".join(params))
            return redirect("products_catalog")
        messages.error(request, "Исправьте ошибки в форме.")
    else:
        initial_data = {}
        if supplier_id:
            initial_data["supplier"] = supplier_id
        if category_id:
            initial_data["category"] = category_id

        form = ProductForm(initial=initial_data)
    return render(
        request,
        "inventory/create_product.html",
        {
            "form": form,
            "next_name": next_name,
            "target": target,
            "selected_products": selected_products,
        },
    )


@test_mode_login_required
def category_create(request):
    next_name = request.GET.get("next", "products_catalog")
    selected_products = request.GET.getlist("products")
    return_url = request.GET.get("return_url")
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            try:
                instance = form.save(commit=False)
                instance.save()
                messages.success(request, "Категория успешно создана!")
                # Возвращаемся в create_product
                # с сохранённым контекстом.
                url = reverse(next_name)
                params = [f"category={instance.pk}"]
                for product_id in selected_products:
                    params.append(f"products={product_id}")
                if return_url:
                    params.append(f"return_url={return_url}")
                if params:
                    url += "?" + "&".join(params)
                return redirect(url)
            except IntegrityError:
                messages.error(request, "Ошибка: Категория с таким названием уже существует.")
        else:
            messages.error(request, "Исправьте ошибки в форме.")
    else:
        form = CategoryForm()
    return render(request, "inventory/category_form.html", {"form": form})


@test_mode_login_required
def product_picker(request):
    query = request.GET.get("q", "")
    target = request.GET.get("target", "receipt")
    category_id = request.GET.get("category")
    customer_id = request.POST.get("customer") or request.GET.get("customer")
    supplier_id = request.POST.get("supplier") or request.GET.get("supplier")
    selected_existing = request.GET.getlist("selected")
    selected_from_products = request.GET.getlist("products")
    selected_ids = {int(x) for x in (selected_existing + selected_from_products) if x.isdigit()}
    warehouse = Warehouse.objects.first()
    warehouse_id = warehouse.id if warehouse else None

    products = Product.objects.with_balances(warehouse_id).select_related("category", "supplier")
    if query:
        products = products.filter(name__icontains=query)
    if category_id:
        products = products.filter(category_id=category_id)
    if request.method == "POST":
        # Товары, выбранные на текущей странице
        selected = request.POST.getlist("products")
        # Все ранее выбранные + новые
        all_products = selected_existing + selected_from_products + selected
        # Только ID
        all_products = [x for x in all_products if x.isdigit()]
        # Убираем дубли
        all_products = list(dict.fromkeys(all_products))
        params = []
        for product_id in all_products:
            params.append(f"products={product_id}")
        if target:
            params.append(f"target={target}")
        supplier_id = request.POST.get("supplier")
        if supplier_id:
            params.append(f"supplier={supplier_id}")
        customer_id = request.POST.get("customer")

        if customer_id:
            params.append(f"customer={customer_id}")
        if target == "sale":
            url = reverse("sale_create")
        else:
            url = reverse("receipt_create")

        if params:
            url += "?" + "&".join(params)
        return redirect(url)

    categories = Category.objects.all()

    return render(
        request,
        "inventory/product_picker.html",
        {
            "products": products,
            "query": query,
            "categories": categories,
            "selected_ids": selected_ids,
            "target": target,
            "customer_id": customer_id,
            "supplier_id": supplier_id,
        },
    )


@test_mode_login_required
def upload_products(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]

        # Базовая валидация на уровне HTTP (формат файла)
        if not file.name.lower().endswith((".xlsx", ".xls")):
            messages.error(request, "Пожалуйста, загружайте только файлы Excel (.xlsx или .xls)")
            return redirect("upload_products")

        try:
            # ВЫЗЫВАЕМ СЕРВИС: передаем файл и получаем результат
            success_count, skip_count = import_products_from_excel(file)

            messages.success(
                request,
                f"Готово! Создано товаров: {success_count}. Пропущено дублей: {skip_count}.",
            )
            return redirect("stock_management")

        except ExcelImportError as e:
            # Перехватываем ошибки сервиса и отдаем пользователю
            messages.error(request, f"Критическая ошибка при импорте: {str(e)}")
            return redirect("upload_products")

    # Если это GET-запрос, просто отдаем HTML-форму
    return render(request, "inventory/upload_products.html")
