import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from rest_framework.generics import get_object_or_404

from ..exceptions import ExcelImportError
from ..forms import CategoryForm, ProductEditForm, ProductForm
from ..models import Category, Product, Supplier, Transaction, Warehouse
from ..navigation import return_destination, url_with_return, with_query_parameter
from ..services import import_products_from_excel


@login_required
def products_catalog_view(request):
    # 1. Получаем категории (для бокового меню)
    categories = Category.objects.all().order_by("name")

    # 2. Получаем уникальные текстовые бренды (для выпадающего фильтра в таблице)
    brands = (
        Product.objects.exclude(brand__isnull=True)
        .exclude(brand__exact="")
        .values_list("brand", flat=True)
        .order_by("brand")
        .distinct()
    )

    products = Product.objects.select_related("category", "supplier").order_by("brand", "name")

    # Фильтр по категории (при клике в боковом меню)
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
        "categories": categories,  # Теперь категории идут отдельно
        "brands": brands,  # А бренды отдельно
        "selected_category": selected_category,
        "page_title": "Каталог товаров",
        "query": query,
    }

    return render(request, "inventory/catalog_page.html", context)


def _product_return_url(request):
    return return_destination(
        request,
        reverse("products_catalog"),
        "home",
        "stock_management",
        "products_catalog",
        "dashboard",
        "movement_report",
        "receipt_detail",
        "sale_detail",
    )


@login_required
def product_detail(request, pk):
    warehouse = Warehouse.objects.first()
    warehouse_id = warehouse.id if warehouse else None

    product = get_object_or_404(
        Product.objects.with_balances(warehouse_id).select_related("supplier").prefetch_related("category"),
        pk=pk,
    )
    # getattr нужен на случай, если склада нет
    balance = getattr(product, "balance", 0)
    stock_profit = getattr(product, "stock_profit", 0)

    transactions = (
        Transaction.objects.filter(product=product)
        .select_related("warehouse", "receipt__supplier", "sale__customer")
        .order_by("-date")
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
            "product_return_url": _product_return_url(request),
        },
    )


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    detail_url = reverse("product_detail", kwargs={"pk": product.pk})
    detail_url = url_with_return(detail_url, _product_return_url(request))
    if request.method == "POST":
        form = ProductEditForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Товар успешно обновлен")
            return redirect(detail_url)
    else:
        form = ProductEditForm(instance=product)
    return render(request, "inventory/product_edit.html", {"form": form, "product": product, "detail_url": detail_url})


@login_required
def product_create(request):
    next_name = request.GET.get("next", "products_catalog")
    selected_products = request.GET.getlist("products")
    supplier_id = request.GET.get("supplier")
    category_id = request.GET.get("category")

    picker_params = request.GET.copy()
    picker_params.pop("next", None)
    picker_params.setlist("products", [item for item in selected_products if item.isdigit()])
    picker_url = reverse("product_picker")

    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.save()
            messages.success(request, "Товар успешно создан!")
            # Если пришли из выбора товаров
            if next_name == "product_picker":
                picker_params.appendlist("products", str(product.pk))
                # A search or category filter can hide the newly created product.
                picker_params.pop("q", None)
                picker_params.pop("category", None)
                return redirect(f"{picker_url}?{picker_params.urlencode()}")
            return redirect("products_catalog")
        messages.error(request, "Исправьте ошибки в форме.")
    else:
        initial_data = {}
        if supplier_id:
            initial_data["supplier"] = supplier_id
        if category_id:
            initial_data["category"] = category_id

        form = ProductForm(initial=initial_data)

    existing_brands = (
        Product.objects.exclude(brand__isnull=True)
        .exclude(brand__exact="")
        .values_list("brand", flat=True)
        .order_by("brand")
        .distinct()
    )

    return render(
        request,
        "inventory/product_create.html",
        {
            "form": form,
            "next_name": next_name,
            "selected_products": selected_products,
            "picker_url": f"{picker_url}?{picker_params.urlencode()}",
            "existing_brands": existing_brands,
        },
    )


@login_required
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
                product_form_url = return_destination(request, "", "product_create")
                if next_name == "product_create" and product_form_url:
                    return redirect(with_query_parameter(product_form_url, "category", instance.pk))
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
    cancel_url = return_destination(request, reverse("products_catalog"), "products_catalog", "product_create")
    return render(request, "inventory/category_form.html", {"form": form, "cancel_url": cancel_url})


@login_required
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
        all_products = selected
        if request.POST.get("selection_complete") != "1":
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

    suppliers = Supplier.objects.all()
    brands = (
        Product.objects.exclude(brand__isnull=True)
        .exclude(brand__exact="")
        .order_by("brand")
        .values_list("brand", flat=True)
        .distinct()
    )

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
            "suppliers": suppliers,
            "brands": brands,
        },
    )


@login_required
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


@login_required
@require_POST
def update_product_category(request):
    try:
        data = json.loads(request.body)
        product_id = data.get("product_id")
        category_id = data.get("category_id")

        product = get_object_or_404(Product, id=product_id)

        if category_id:
            category = get_object_or_404(Category, id=category_id)
            product.category = category
        else:
            product.category = None

        product.save(update_fields=["category"])

        return JsonResponse({"status": "success"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
