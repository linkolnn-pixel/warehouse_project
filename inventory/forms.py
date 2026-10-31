from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone
from django_select2.forms import ModelSelect2Widget

from .models import (
    Category,
    Customer,
    Product,
    Receipt,
    ReceiptItem,
    Sale,
    SaleItem,
    Supplier,
    Warehouse,
)


# Формы для товаров и Excel
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "category",
            "supplier",
            "unit",
            "quantity_value",
            "measure_unit",
            "cost_price",
            "sale_price",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "sku": forms.TextInput(attrs={"class": "form-control"}),
            "supplier": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "unit": forms.TextInput(attrs={"class": "form-control"}),
            "quantity_value": forms.NumberInput(attrs={"class": "form-control"}),
            "measure_unit": forms.TextInput(attrs={"class": "form-control"}),
            "cost_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "sale_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


class ProductEditForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "category",
            "supplier",
            "sku",
            "cost_price",
            "sale_price",
            "unit",
            "quantity_value",
            "measure_unit",
        ]
        labels = {
            "name": "Наименование",
            "category": "Бренд",
            "supplier": "Поставщик",
            "sku": "Артикул",
            "cost_price": "Закупочная цена",
            "sale_price": "Цена продажи",
            "quantity_value": "Объем / вес",
            "measure_unit": "Ед. измерения объема",
            "unit": "Единица учета",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "supplier": forms.Select(attrs={"class": "form-select"}),
            "sku": forms.TextInput(attrs={"class": "form-control"}),
            "cost_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "sale_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "unit": forms.TextInput(attrs={"class": "form-control"}),
            "quantity_value": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "measure_unit": forms.Select(attrs={"class": "form-select"}),
        }


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["company_name", "inn"]
        widgets = {
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "inn": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("company_name"):
            self.add_error("company_name", "Введите название компании")
        return cleaned_data


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["last_name", "first_name"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        first_name = cleaned_data.get("first_name")
        last_name = cleaned_data.get("last_name")

        if not first_name:
            self.add_error("first_name", "Введите имя клиента")

        if not last_name:
            self.add_error("last_name", "Введите фамилию клиента")

        if first_name and last_name:
            exists = (
                Customer.objects.filter(
                    first_name__iexact=first_name.strip(),
                    last_name__iexact=last_name.strip(),
                )
                .exclude(pk=self.instance.pk)
                .exists()
            )

            if exists:
                raise forms.ValidationError("Клиент с таким именем и фамилией уже существует.")

        return cleaned_data


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"class": "form-control", "required": "required"})}


class ExcelUploadForm(forms.Form):
    file = forms.FileField(label="Выберите файл Excel (.xlsx)")


class ReceiptForm(forms.ModelForm):
    class Meta:
        model = Receipt
        fields = ["date", "warehouse", "supplier", "comment", "delivery_cost"]
        widgets = {
            "date": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local", "class": "form-control"}
            ),
            "warehouse": forms.Select(attrs={"class": "form-select"}),
            "supplier": forms.Select(attrs={"class": "form-select"}),
            "comment": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "delivery_cost": forms.NumberInput(attrs={"class": "form-control text-end", "step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["supplier"].queryset = Supplier.objects.filter(is_deleted=False)

        # если склад не выбран — ставим первый
        if not self.instance.pk:
            first_warehouse = Warehouse.objects.first()
            if first_warehouse:
                self.fields["warehouse"].initial = first_warehouse

        # Установка даты
        if not self.instance.pk and not self.initial.get("date"):
            # Новый документ: ставим текущее время
            self.initial["date"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")
        elif self.instance.pk and getattr(self.instance, "date", None):
            # Редактирование: форматируем дату из БД
            self.initial["date"] = timezone.localtime(self.instance.date).strftime("%Y-%m-%dT%H:%M")


class ReceiptItemForm(forms.ModelForm):
    balance = forms.DecimalField(
        required=False,
        disabled=True,
        label="Остаток",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=ModelSelect2Widget(
            model=Product,
            search_fields=[
                "name__icontains",
                "sku__icontains",
                "internal_code__icontains",
            ],
        ),
        label="Товар",
    )

    class Meta:
        model = ReceiptItem
        fields = [
            "product",
            "balance",
            "quantity",
            "cost_price",
            "sale_price",
        ]
        widgets = {
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "cost_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "sale_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        product = None
        if self.instance and self.instance.pk:
            product = getattr(self.instance, "product", None)
        if product:
            self.fields["cost_price"].initial = product.cost_price
            self.fields["sale_price"].initial = product.sale_price or 0


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ["date", "warehouse", "customer", "comment", "delivery_expense"]
        widgets = {
            "date": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local", "class": "form-control"}
            ),
            "warehouse": forms.Select(attrs={"class": "form-select"}),
            "customer": forms.Select(
                attrs={
                    "class": "form-select",
                    "required": "required",
                }
            ),
            "comment": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "delivery_expense": forms.NumberInput(attrs={"class": "form-control text-end", "step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["customer"].queryset = Customer.objects.filter(is_deleted=False)

        if not self.instance.pk and not self.initial.get("warehouse"):
            warehouse = Warehouse.objects.first()
            if warehouse:
                self.initial["warehouse"] = warehouse.pk

            # Установка даты
            if not self.instance.pk and not self.initial.get("date"):
                self.initial["date"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")
            elif self.instance.pk and getattr(self.instance, "date", None):
                self.initial["date"] = timezone.localtime(self.instance.date).strftime("%Y-%m-%dT%H:%M")

        self.fields["customer"].required = True
        self.fields["customer"].error_messages = {"required": "Пожалуйста, выберите клиента для совершения продажи."}


class SaleItemForm(forms.ModelForm):
    balance = forms.DecimalField(
        required=False,
        disabled=True,
        label="Остаток",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=ModelSelect2Widget(
            model=Product,
            search_fields=[
                "name__icontains",
                "sku__icontains",
                "internal_code__icontains",
            ],
        ),
        label="Товар",
    )

    class Meta:
        model = SaleItem
        fields = ["product", "balance", "quantity", "sale_price"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1, "step": 1}),
            "sale_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        warehouse = kwargs.pop("warehouse", None)
        super().__init__(*args, **kwargs)

        self.warehouse = warehouse

        if self.instance.pk:
            product = self.instance.product
        else:
            product = self.initial.get("product")

        if product:
            self.fields["balance"].initial = product.get_balance(warehouse) if warehouse else 0
            self.fields["sale_price"].initial = product.sale_price


ReceiptItemFormSet = inlineformset_factory(Receipt, ReceiptItem, form=ReceiptItemForm, extra=5, can_delete=True)

SaleItemFormSet = inlineformset_factory(Sale, SaleItem, form=SaleItemForm, extra=1, can_delete=True)
