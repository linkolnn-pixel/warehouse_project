from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import inlineformset_factory
from django.shortcuts import redirect, render
from rest_framework.generics import get_object_or_404

from inventory.decorators import test_mode_login_required
from inventory.forms import ReceiptForm, ReceiptItemForm, SaleForm, SaleItemForm
from inventory.models import Product, Receipt, ReceiptItem, Sale, SaleItem, Warehouse


@test_mode_login_required
@transaction.atomic
def receipt_create(request):
    warehouse = Warehouse.objects.first()
    if not warehouse:
        messages.error(request, "Нет склада. Создайте склад.")
        return redirect("stock_management")

    selected_products = request.POST.getlist("products") or request.GET.getlist("products")
    supplier_id = request.POST.get("supplier") or request.GET.get("supplier")

    product_ids = [int(x) for x in selected_products if x.isdigit()]
    products = Product.objects.filter(id__in=product_ids).select_related("category")

    ReceiptItemFormSetDynamic = inlineformset_factory(
        Receipt,
        ReceiptItem,
        form=ReceiptItemForm,
        extra=len(products) if products else 1,
        can_delete=True,
    )

    if request.method == "POST":
        post_data = request.POST.copy()
        if not post_data.get("supplier") and supplier_id:
            post_data["supplier"] = supplier_id

        form = ReceiptForm(post_data)
        if form.is_valid():
            receipt = form.save(commit=False)
            receipt.warehouse = form.cleaned_data["warehouse"]
            receipt.save()

            formset = ReceiptItemFormSetDynamic(request.POST, instance=receipt)
            if formset.is_valid():
                items = formset.save(commit=False)
                for item in items:
                    item.receipt = receipt
                    item.save()
                for obj in formset.deleted_objects:
                    obj.delete()

                try:
                    receipt.post()  # Автоматически проводим документ
                    messages.success(request, f"Приход №{receipt.number} успешно создан и проведен!")
                except Exception as e:
                    messages.warning(
                        request,
                        f"Приход сохранен как черновик, но провести не удалось: {e}",
                    )

                return redirect("receipt_detail", pk=receipt.pk)
    else:
        initial_data = {"warehouse": warehouse}
        if supplier_id:
            initial_data["supplier"] = supplier_id

        form = ReceiptForm(initial=initial_data)
        initial = [
            {
                "product": p,
                "quantity": 1,
                "cost_price": p.cost_price,
                "sale_price": p.sale_price,
            }
            for p in products
        ]

        receipt = Receipt(warehouse=warehouse)
        formset = ReceiptItemFormSetDynamic(instance=receipt, initial=initial)

    return render(
        request,
        "inventory/receipt_create.html",
        {"form": form, "formset": formset, "supplier_id": supplier_id},
    )


@test_mode_login_required
def receipt_post(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    try:
        receipt.post()
        messages.success(request, "Приход проведен")
    except Exception as e:
        messages.error(request, str(e))
    return redirect("receipt_detail", pk=pk)


@test_mode_login_required
def receipt_detail(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    return render(request, "inventory/receipt_detail.html", {"receipt": receipt})


@test_mode_login_required
@transaction.atomic
def sale_create(request):
    warehouse = Warehouse.objects.first()
    if not warehouse:
        messages.error(request, "Нет склада.")
        return redirect("stock_management")

    selected_products = request.POST.getlist("products") or request.GET.getlist("products")
    customer_id = request.POST.get("customer") or request.GET.get("customer")

    product_ids = [int(x) for x in selected_products if x.isdigit()]
    products = Product.objects.filter(id__in=product_ids).select_related("category")

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
            submitted_product_ids = []
            for item_form in formset:
                if item_form.cleaned_data and not item_form.cleaned_data.get("DELETE"):
                    product = item_form.cleaned_data.get("product")
                    if product:
                        submitted_product_ids.append(product.id)

            products_with_balances = Product.objects.with_balances(warehouse.id).filter(id__in=submitted_product_ids)
            # Делаем удобный словарь {id_товара: остаток}
            balances_dict = {p.id: getattr(p, "balance", 0) for p in products_with_balances}

            stock_error = False
            for item_form in formset:
                if not item_form.cleaned_data or item_form.cleaned_data.get("DELETE"):
                    continue

                product = item_form.cleaned_data.get("product")
                quantity = item_form.cleaned_data.get("quantity")
                if not product or not quantity:
                    continue

                # Берем остаток из нашего словаря в памяти (без запросов к БД!)
                current_stock = balances_dict.get(product.id, 0)

                if quantity > current_stock:
                    messages.error(
                        request,
                        f"Недостаточно товара: {product.name}. " f"Доступно: {current_stock}, запрошено: {quantity}.",
                    )
                    stock_error = True

            if stock_error:
                # Если была ошибка остатков, откатываем транзакцию неявным образом
                return render(
                    request,
                    "inventory/sale_create.html",
                    {"form": form, "formset": formset},
                )

            sale = form.save()
            formset.instance = sale
            items = formset.save(commit=False)
            for item in items:
                item.sale = sale
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()

            try:
                sale.post()  # Автоматически проводим документ
                messages.success(request, f"Продажа №{sale.id} успешно создана и проведена!")
            except ValidationError as e:
                # На случай, если в момент сохранения кто-то другой уже купил товар
                messages.warning(request, f"Продажа создана, но не проведена: {e}")

            return redirect("sale_detail", pk=sale.pk)
    else:
        initial_data = {"warehouse": warehouse}
        if customer_id:
            initial_data["customer"] = customer_id

        form = SaleForm(initial=initial_data)
        initial = [{"product": p, "quantity": 1, "sale_price": p.sale_price} for p in products]

        sale = Sale()
        formset = SaleItemFormSetDynamic(instance=sale, initial=initial)

        for form_item in formset:
            prod = None
            if form_item.instance.pk and form_item.instance.product:
                prod = form_item.instance.product
            elif form_item.initial.get("product"):
                prod = form_item.initial.get("product")

            if prod:
                balance_value = prod.get_balance(warehouse)
                form_item.initial["balance"] = balance_value

    return render(
        request,
        "inventory/sale_create.html",
        {"form": form, "formset": formset, "customer_id": customer_id},
    )


@test_mode_login_required
def sale_post(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    try:
        sale.post()
        messages.success(request, "Продажа проведена")

    except ValidationError as e:
        error_msg = ", ".join(e.messages) if hasattr(e, "messages") else str(e)
        messages.error(request, error_msg)

    except Exception as e:
        # Отлов любых других непредвиденных ошибок
        messages.error(request, f"Ошибка при проведении: {str(e)}")

    return redirect("sale_detail", pk=pk)


@test_mode_login_required
def sale_detail(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    return render(request, "inventory/sale_detail.html", {"sale": sale})


@test_mode_login_required
def sale_unpost(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    try:
        sale.unpost()
        messages.success(
            request,
            f"Проведение продажи №{sale.number} отменено. Документ доступен для редактирования.",
        )
    except Exception as e:
        messages.error(request, f"Ошибка отмены: {str(e)}")
    return redirect("sale_detail", pk=pk)


@test_mode_login_required
def receipt_unpost(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    try:
        receipt.unpost()
        messages.success(
            request,
            f"Проведение прихода №{receipt.number} отменено. Документ доступен для редактирования.",
        )
    except Exception as e:
        messages.error(request, f"Ошибка отмены: {str(e)}")
    return redirect("receipt_detail", pk=pk)


@test_mode_login_required
@transaction.atomic
def sale_edit(request, pk):
    sale = get_object_or_404(Sale, pk=pk)

    if sale.posted:
        messages.error(
            request,
            "Нельзя редактировать проведенный документ. Сначала отмените проведение.",
        )
        return redirect("sale_detail", pk=sale.pk)

    warehouse = sale.warehouse
    SaleItemFormSetDynamic = inlineformset_factory(Sale, SaleItem, form=SaleItemForm, extra=0, can_delete=True)

    if request.method == "POST":
        form = SaleForm(request.POST, instance=sale)
        formset = SaleItemFormSetDynamic(request.POST, instance=sale)

        if form.is_valid() and formset.is_valid():
            sale = form.save()
            formset.save()
            messages.success(request, f"Продажа №{sale.id} успешно обновлена.")
            return redirect("sale_detail", pk=sale.pk)
        else:
            # === ОТЛАДКА: ВЫВОД ОШИБОК ===
            print("--- ОШИБКИ ПРОДАЖИ ---")
            print("Ошибки шапки:", form.errors)
            print("Ошибки товаров:", formset.errors)
            print("Общие ошибки:", formset.non_form_errors())
            messages.error(
                request,
                "Ошибка сохранения! Проверьте данные. Подробности в консоли сервера.",
            )
    else:
        form = SaleForm(instance=sale)
        formset = SaleItemFormSetDynamic(instance=sale)

        for form_item in formset:
            prod = None
            if form_item.instance.pk and form_item.instance.product:
                prod = form_item.instance.product
            elif form_item.initial.get("product"):
                prod = form_item.initial.get("product")

            if prod:
                balance_value = prod.get_balance(warehouse)
                form_item.initial["balance"] = balance_value

    return render(
        request,
        "inventory/sale_create.html",
        {"form": form, "formset": formset, "is_edit": True, "sale": sale},
    )


@test_mode_login_required
@transaction.atomic
def receipt_edit(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)

    if receipt.posted:
        messages.error(
            request,
            "Нельзя редактировать проведенный документ. Сначала отмените проведение.",
        )
        return redirect("receipt_detail", pk=receipt.pk)

    warehouse = receipt.warehouse
    ReceiptItemFormSetDynamic = inlineformset_factory(
        Receipt, ReceiptItem, form=ReceiptItemForm, extra=0, can_delete=True
    )

    if request.method == "POST":
        form = ReceiptForm(request.POST, instance=receipt)
        formset = ReceiptItemFormSetDynamic(request.POST, instance=receipt)

        if form.is_valid() and formset.is_valid():
            receipt = form.save()
            formset.save()
            messages.success(request, f"Приход №{receipt.id} успешно обновлен.")
            return redirect("receipt_detail", pk=receipt.pk)
        else:
            # === ОТЛАДКА: ВЫВОД ОШИБОК ===
            print("--- ОШИБКИ ПРИХОДА ---")
            print("Ошибки шапки:", form.errors)
            print("Ошибки товаров:", formset.errors)
            print("Общие ошибки:", formset.non_form_errors())
            messages.error(
                request,
                "Ошибка сохранения! Проверьте данные. Подробности в консоли сервера.",
            )
    else:
        form = ReceiptForm(instance=receipt)
        formset = ReceiptItemFormSetDynamic(instance=receipt)

        for form_item in formset:
            if form_item.instance.product_id:
                form_item.balance = form_item.instance.product.get_balance(warehouse)

    return render(
        request,
        "inventory/receipt_create.html",
        {"form": form, "formset": formset, "is_edit": True, "receipt": receipt},
    )
