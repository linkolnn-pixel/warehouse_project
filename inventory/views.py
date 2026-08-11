import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from .models import Product, Warehouse, Transaction, Category, Counterparty, Receipt, ReceiptItem, Sale, SaleItem
from .forms import ProductForm, CounterpartyForm, CategoryForm, ProductEditForm, ReceiptForm, ReceiptItemForm, SaleForm, SaleItemForm
from decimal import Decimal, InvalidOperation
from django.urls import reverse
from django.forms import inlineformset_factory
from rest_framework.viewsets import ReadOnlyModelViewSet, ModelViewSet
from .serializers import ProductSerializer, WarehouseSerializer, WarehouseStockSerializer,ReceiptSerializer, SaleSerializer
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ValidationError


@login_required
def stock_management_view(request):
    products = Product.objects.select_related('category')
    warehouse = Warehouse.objects.first()  # Берем первый склад для отображения
    categories = Category.objects.all()
    # Формируем данные для таблицы
    rows = []
    for product in products:
        balance = 0
        stock_profit = 0
        if warehouse:
            balance = product.get_balance(warehouse)
            stock_profit = product.get_stock_profit(warehouse)
        rows.append({
            'product': product,
            'balance': balance,
            'stock_profit': stock_profit,
            'warehouse_name': warehouse.name if warehouse else 'Нет складов'
        })
    return render(request, 'inventory/stock_page.html', {
        'page_title': 'Управление остатками',
        'rows': rows,
        'warehouse': warehouse,
        'categories': categories,
    })

@login_required
@transaction.atomic
def upload_products(request):
    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']
        if not file.name.lower().endswith(('.xlsx', '.xls')):
            messages.error(request, "Пожалуйста, загружайте только файлы Excel (.xlsx или .xls)")
            return redirect('upload_products')
        try:
            df = pd.read_excel(file)
            # Нормализация заголовков
            df.columns = df.columns.str.strip().str.lower()
            required_cols = ['наименование', 'закупочная цена', 'цена продажи']
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                messages.error(request, f"В файле не найдены колонки: {', '.join(missing)}")
                return redirect('upload_products')
            success_count = 0
            skip_count = 0
            for index, row in df.iterrows():
                # 1. Наименование
                name = str(row['наименование']).strip()
                if not name or name.lower() == 'nan':
                    continue

                # 2. БРЕНД (КАТЕГОРИЯ)
                # Ищем колонку 'бренд' или 'category_name' в Excel
                brand_val = row.get('бренд', '') or row.get('category_name', '')
                if pd.notna(brand_val):
                    brand_name = str(brand_val).strip()
                else:
                    brand_name = ''
                category_obj = None
                if brand_name:
                    # Создаем категорию (если нет) и привязываем товар к ней
                    category_obj, created = Category.objects.get_or_create(
                        name=brand_name,
                        parent=None,
                    )
                    if created:
                        messages.info(request, f"Автоматически создана категория-бренд: {brand_name}")

                # 3. Артикул (SKU)
                sku_raw = row.get('артикул', '')
                if pd.notna(sku_raw):
                    sku = str(sku_raw).strip()
                else:
                    sku = ''
                # Проверка на дубликат
                search_kwargs = {'sku': sku} if sku else {'name': name}
                if Product.objects.filter(**search_kwargs).exists():
                    messages.warning(request, f"Строка {index + 2}: Товар '{name}' уже существует. Пропущено.")
                    skip_count += 1
                    continue

                # 4. Цены
                try:
                    cost_str = str(row['закупочная цена']).replace(',', '.')
                    sale_str = str(row['цена продажи']).replace(',', '.')
                    cost_price = Decimal(cost_str)
                    sale_price = Decimal(sale_str)
                except (InvalidOperation, ValueError, TypeError):
                    messages.warning(request, f"Строка {index + 2}: Ошибка в ценах для '{name}'. Пропущено.")
                    continue

                # 5. Вес, объем, ед. изм.
                vol_raw = row.get('объем', 0)
                weight_raw = row.get('вес', 0)
                final_quantity = Decimal('0')
                final_measure = 'мл'
                final_unit = 'шт'
                unit_raw = str(row.get('ед. изм.', '')).strip().lower()
                if unit_raw:
                    final_unit = unit_raw
                if pd.notna(vol_raw) and str(vol_raw).lower() != 'nan':
                    try:
                        val = Decimal(str(vol_raw).replace(',', '.'))
                        if val > 0:
                            final_quantity = val
                            final_measure = 'мл'
                    except:
                        pass
                elif pd.notna(weight_raw) and str(weight_raw).lower() != 'nan':
                    try:
                        val = Decimal(str(weight_raw).replace(',', '.'))
                        if val > 0:
                            final_quantity = val
                            final_measure = 'г'
                    except:
                        pass

                # 6. Поставщик
                supplier_name_raw = row.get('поставщик', '') or row.get('supplier', '')
                supplier_name = str(supplier_name_raw).strip() if pd.notna(supplier_name_raw) and str(
                    supplier_name_raw).lower() != 'nan' else ''
                supplier_obj = None
                if supplier_name:
                    # Ищем поставщика по имени. Если нет - создаем.
                    supplier_obj, created = Counterparty.objects.get_or_create(
                        company_name = supplier_name,
                        defaults = { 'type': 'supplier' }
                    )
                    if created:
                        messages.info(request, f"Автоматически создан поставщик: {supplier_name}")
                # 7. Создание товара
                Product.objects.create(
                    name = name,
                    category = category_obj,
                    supplier = supplier_obj,
                    sku = sku,
                    unit = final_unit,
                    cost_price = cost_price,
                    sale_price = sale_price,
                    quantity_value = final_quantity,
                    measure_unit = final_measure
                )
                success_count += 1
            messages.success(request,
                             f"Готово! Создано товаров: {success_count}. Пропущено дублей: {skip_count}.")
            return redirect('stock_management')
        except Exception as e:
            messages.error(request, f"Критическая ошибка: {str(e)}")
            return redirect('upload_products')
    return render(request, 'inventory/upload_products.html')

@login_required
def create_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.save()
            messages.success(request, "Товар успешно создан!")
            return redirect('products_catalog')
        else:
            messages.error(request, "Исправьте ошибки в форме.")
    else:
        form = ProductForm()
    return render(request, 'inventory/create_product.html', {'form': form})

@login_required
def counterparty_create(request):
    next_name = request.GET.get("next", "products_catalog")
    if request.method == "POST":
        form = CounterpartyForm(request.POST, counterparty_type="supplier")
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.type = "supplier"
            try:
                supplier.save()
                messages.success(request, f"Поставщик «{supplier.company_name}» создан.")
                return redirect(next_name)
            except IntegrityError:
                messages.error(request, "Такой поставщик уже существует.")
    else:
        form = CounterpartyForm( counterparty_type="supplier" )
    return render(request, "inventory/counterparty_form.html", { "form": form })

@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related('category', 'supplier'), pk=pk)
    warehouse = Warehouse.objects.first()
    balance = 0
    stock_profit = 0
    if warehouse:
        balance = product.get_balance(warehouse)
        stock_profit = product.get_stock_profit(warehouse)
    transactions = (
        Transaction.objects
        .filter(product=product)
        .select_related('warehouse', 'counterparty')
        .order_by('-date')
    )
    return render(
        request,
        'inventory/product_detail.html',
        {
            'product': product,
            'transactions': transactions,
            'warehouse': warehouse,
            'balance': balance,
            'stock_profit': stock_profit,
        }
    )

@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductEditForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Товар успешно обновлен")
            return redirect('product_detail', pk=product.pk)
    else:
        form = ProductEditForm(instance=product)
    return render(request, 'inventory/product_edit.html', {'form': form, 'product': product})

@login_required
def category_create(request):
    next_url = request.GET.get('next')
    if next_url and not next_url.startswith('/'):
        redirect_name = next_url
    else:
        redirect_name = 'products_catalog'
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            try:
                instance = form.save(commit=False)
                instance.save()
                messages.success(request, "Категория успешно создана!")
                return redirect(redirect_name)
            except IntegrityError:
                messages.error(request, "Ошибка: Категория с таким названием или slug уже существует.")
                return render(request, 'inventory/category_form.html', {'form': form})
        else:
            messages.error(request, "Исправьте ошибки в форме.")
            return render(request, 'inventory/category_form.html', {'form': form})
    form = CategoryForm()
    return render(request, 'inventory/category_form.html', {'form': form})

@login_required
def movement_report(request):
    qs = (
        Transaction.objects
        .select_related(
            'product',
            'warehouse',
            'counterparty',
            'receipt',
            'sale',
        )
        .order_by('-date')
    )
    return render(request, 'inventory/movement_report.html', {'transactions': qs})

@login_required
def products_catalog_view(request):
    # Бренды = корневые категории
    brands = (
        Category.objects
        .filter(parent__isnull=True)
        .order_by('name')
    )

    # Все товары
    products = (
        Product.objects
        .select_related('category', 'supplier')
        .order_by('brand', 'name')
    )

    # Фильтр по бренду/категории
    selected_cat_id = request.GET.get('cat')
    selected_category = None

    if selected_cat_id:
        selected_category = get_object_or_404(
            Category,
            id=selected_cat_id
        )

        products = products.filter(
            category=selected_category
        )

    # Поиск
    query = request.GET.get('q', '').strip()

    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(sku__icontains=query) |
            Q(internal_code__icontains=query)
        )

    context = {
        'products': products,
        'brands': brands,
        'selected_category': selected_category,
        'page_title': 'Каталог товаров',
        'query': query,
    }

    return render(
        request,
        'inventory/catalog_page.html',
        context
    )
@login_required
def receipt_create(request):
    warehouse = Warehouse.objects.first()
    if not warehouse:
        messages.error(request, "Нет склада. Создайте склад.")
        return redirect('stock_management')
    selected_products = request.GET.getlist('products')
    product_ids = [
        int(x)
        for x in selected_products
        if x.isdigit()
    ]
    products = Product.objects.filter(id__in=product_ids).select_related('category')
    ReceiptItemFormSetDynamic = inlineformset_factory(
        Receipt,
        ReceiptItem,
        form=ReceiptItemForm,
        extra=len(products) if products else 1,
        can_delete=True
    )
    if request.method == "POST":
        form = ReceiptForm(request.POST)
        if form.is_valid():
            receipt = form.save(commit=False)
            receipt.warehouse = form.cleaned_data['warehouse']
            receipt.save()
            formset = ReceiptItemFormSetDynamic(
                request.POST,
                instance=receipt
            )
            if formset.is_valid():
                items = formset.save(commit=False)
                for item in items:
                    item.receipt = receipt
                    item.save()
                messages.success(request, f"Приход №{receipt.number} создан")
                return redirect('receipt_detail', pk=receipt.pk)
    else:
        form = ReceiptForm(initial={'warehouse': warehouse})
        initial = []
        for product in products:
            initial.append(
                {
                    'product': product,
                    'quantity': 1,
                    'cost_price': product.cost_price,
                    'sale_price': product.sale_price,
                }
            )
        receipt = Receipt()
        formset = ReceiptItemFormSetDynamic(
            instance=receipt,
            initial=initial
        )
    return render(
        request,
        'inventory/receipt_create.html',
        {
            'form': form,
            'formset': formset,
        }
    )

@login_required
def receipt_detail(request, pk):
    receipt = get_object_or_404(
        Receipt,
        pk=pk
    )
    return render(request, 'inventory/receipt_detail.html', {'receipt':receipt})

@login_required
def receipt_post(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    try:
        receipt.post()
        messages.success(request, "Приход проведен")
    except Exception as e:
        messages.error(request, str(e))
    return redirect('receipt_detail', pk=pk)

@login_required
def sale_create(request):
    warehouse = Warehouse.objects.first()
    if not warehouse:
        messages.error(request, "Нет склада.")
        return redirect("stock_management")
    selected_products = request.GET.getlist("products")
    customer_id = request.GET.get("customer")
    product_ids = [
        int(x)
        for x in selected_products
        if x.isdigit()
    ]
    products = Product.objects.filter(id__in=product_ids).select_related("category")
    selected_products_string = ",".join(selected_products)
    SaleItemFormSetDynamic = inlineformset_factory(
        Sale,
        SaleItem,
        form=SaleItemForm,
        extra=len(products) if products else 1,
        can_delete=True,
    )
    if request.method == "POST":
        form = SaleForm(request.POST)
        sale = Sale()
        formset = SaleItemFormSetDynamic(request.POST, instance=sale)
        if form.is_valid() and formset.is_valid():
            stock_error = False
            for item_form in formset:
                if not item_form.cleaned_data:
                    continue
                if item_form.cleaned_data.get("DELETE"):
                    continue
                product = item_form.cleaned_data.get("product")
                quantity = item_form.cleaned_data.get("quantity")
                if not product or not quantity:
                    continue
                current_stock = product.get_balance(warehouse)
                if quantity > current_stock:
                    messages.error( request, f"Недостаточно товара: " f"{product.name}. " f"Доступно: {current_stock}, " f"запрошено: {quantity}.")
                    stock_error = True
            # Если товара недостаточно —
            # НЕ сохраняем продажу и возвращаем форму.
            if stock_error:
                return render( request, "inventory/sale_create.html", { "form": form, "formset": formset, })
            # ЕСЛИ ОСТАТКОВ ДОСТАТОЧНО — СОХРАНЯЕМ
            sale = form.save()
            formset.instance = sale
            items = formset.save(commit=False)
            for item in items:
                item.sale = sale
                item.save()
            # Удаляем отмеченные строки
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f"Продажа №{sale.id} создана")
            return redirect("sale_detail", pk=sale.pk)
    else:

        form = SaleForm(
            initial={
                "warehouse": warehouse,
                "customer": customer_id
            }
        )
        initial = []
        for product in products:
            initial.append(
                {
                    "product": product,
                    "quantity": 1,
                    "sale_price": product.sale_price,
                    "balance": product.get_balance(warehouse),
                }
            )
        sale = Sale()
        formset = SaleItemFormSetDynamic(
            instance=sale,
            initial=initial,
        )
    return render(
        request,
        "inventory/sale_create.html",
        {
            "form": form,
            "formset": formset,
        }
    )

@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    return render(request, 'inventory/sale_detail.html', {'sale':sale})

@login_required
def sale_post(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    try:
        sale.post()
        messages.success(request, "Продажа проведена")
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('sale_detail', pk=pk)

@login_required
def product_picker(request):
    query = request.GET.get('q', '')
    target = request.GET.get(
        'target',
        'receipt'
    )
    customer_id = request.GET.get('customer')
    category_id = request.GET.get('category')
    supplier_id = request.GET.get('supplier')
    # уже добавленные товары
    selected_existing = request.GET.getlist('selected')
    selected_ids = {
        int(x)
        for x in selected_existing
        if x.isdigit()
    }
    products = Product.objects.all().select_related(
        'category',
        'supplier'
    )
    if query:
        products = products.filter(name__icontains=query)
    if category_id:
        products = products.filter(category_id=category_id)
    if supplier_id:
        products = products.filter(supplier_id=supplier_id)
    if request.method == "POST":
        selected = request.POST.getlist('products')
        all_products = []
        # старые выбранные товары
        all_products.extend(selected_existing)
        # новые выбранные товары
        all_products.extend(selected)
        # убрать дубли
        all_products = list(dict.fromkeys(all_products))
        params = "&".join(
            [
                f"products={p}"
                for p in all_products
            ]
        )
        if customer_id:
            params += f"&customer={customer_id}"
        if target == "sale":
            url = reverse("sale_create")
        else:
            url = reverse("receipt_create")
        return redirect(f"{url}?{params}")
    categories = Category.objects.all()
    suppliers = Counterparty.objects.filter(type='supplier')
    warehouse = Warehouse.objects.first()
    if warehouse:
        for product in products:
            product.balance = product.get_balance(warehouse)
    else:
        for product in products:
            product.balance = 0
    return render(
        request,
        'inventory/product_picker.html',
        {
            'products': products,
            'query': query,
            'categories': categories,
            'suppliers': suppliers,
            'selected_ids': selected_ids,
        }
    )

@login_required
def customer_create(request):
    next_name = request.GET.get(
        "next",
        "sale_create"
    )
    selected_products = request.GET.getlist("products")
    if request.method == "POST":
        form = CounterpartyForm(request.POST, counterparty_type="customer")
        if form.is_valid():
            customer = form.save(commit=False)
            customer.type = "customer"
            try:
                customer.save()
                messages.success(request, f"Клиент «{customer.first_name} {customer.last_name}» создан.")
                # Формируем URL обратно
                url = reverse(next_name)
                params = []
                # Передаем созданного клиента
                params.append(f"customer={customer.pk}")
                # Возвращаем все ранее выбранные товары
                for product_id in selected_products:
                    params.append(f"products={product_id}")
                if params:
                    url += "?" + "&".join(params)
                return redirect(url)
            except IntegrityError:
                messages.error(request, "Такой клиент уже существует.")
    else:
        form = CounterpartyForm(counterparty_type="customer")
    return render(request, "inventory/customer_form.html", {"form": form})

@login_required
def customers_list(request):
    customers = (
        Counterparty.objects
        .filter(type='customer')
        .order_by('company_name', 'last_name', 'first_name')
    )
    return render(request, 'inventory/customers.html', {'customers': customers})

@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(
        Counterparty,
        pk=pk,
        type='customer'
    )
    sales = (
        Sale.objects
        .filter(customer=customer)
        .prefetch_related('items__product')
        .order_by('-date', '-id')
    )
    total_sales = Decimal('0.00')
    sales_count = sales.count()
    for sale in sales:
        sale_total = Decimal('0.00')
        for item in sale.items.all():
            sale_total += (
                Decimal(str(item.quantity)) *
                Decimal(str(item.sale_price))
            )
        sale.calculated_total = sale_total
        total_sales += sale_total
    return render(
        request,
        'inventory/customer_detail.html',
        {
            'customer': customer,
            'sales': sales,
            'sales_count': sales_count,
            'total_sales': total_sales,
        }
    )

class ProductViewSet(ReadOnlyModelViewSet):
    queryset = Product.objects.select_related(
        'category',
        'supplier',
    ).all()
    serializer_class = ProductSerializer

class WarehouseViewSet(ReadOnlyModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer

    @action(
        detail=True,
        methods=['get'],
        url_path='stock'
    )
    def stock(self, request, pk=None):
        warehouse = self.get_object()

        products = Product.objects.select_related(
            'category',
            'supplier'
        ).all()

        search = request.query_params.get('q')

        if search:
            from django.db.models import Q

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
    @transaction.atomic
    def post_receipt(self, request, pk=None):
        receipt = self.get_object()

        if receipt.posted:
            return Response(
                {
                    'detail': 'Приход уже проведён.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            receipt.post()
        except Exception as e:
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
    @transaction.atomic
    def post_sale(self, request, pk=None):
        sale = self.get_object()

        if sale.posted:
            return Response(
                {
                    'detail': 'Продажа уже проведена.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            sale.post()

        except ValidationError as e:
            return Response(
                {
                    'detail': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            SaleSerializer(
                sale,
                context={'request': request}
            ).data,
            status=status.HTTP_200_OK
        )