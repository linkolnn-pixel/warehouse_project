from django import forms
from .models import Transaction, Product, Warehouse, Counterparty, Category, Receipt, ReceiptItem, Sale, SaleItem
from django.forms import inlineformset_factory
from django_select2.forms import ModelSelect2Widget



# Формы для товаров и Excel (чтобы работали кнопки создания и загрузки)
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'sku', 'category', 'supplier', 'unit', 'quantity_value', 'measure_unit', 'cost_price',
                  'sale_price']

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity_value': forms.NumberInput(attrs={'class': 'form-control'}),
            'measure_unit': forms.TextInput(attrs={'class': 'form-control'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'sale_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class ProductEditForm(forms.ModelForm):

    class Meta:
        model = Product

        fields = [
            'name',
            'category',
            'supplier',
            'sku',
            'cost_price',
            'sale_price',
            'unit',
            'quantity_value',
            'measure_unit',
        ]

        labels = {
            'name': 'Наименование',
            'category': 'Бренд',
            'supplier': 'Поставщик',
            'sku': 'Артикул',
            'cost_price': 'Закупочная цена',
            'sale_price': 'Цена продажи',
            'quantity_value': 'Объем / вес',
            'measure_unit': 'Ед. измерения объема',
            'unit': 'Единица учета',
        }

        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control'
            }),

            'category': forms.Select(attrs={
                'class': 'form-select'
            }),

            'supplier': forms.Select(attrs={
                'class': 'form-select'
            }),

            'sku': forms.TextInput(attrs={
                'class': 'form-control'
            }),

            'cost_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),

            'sale_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),

            'unit': forms.TextInput(attrs={
                'class': 'form-control'
            }),

            'quantity_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),

            'measure_unit': forms.Select(attrs={
                'class': 'form-select'
            }),
        }


class CounterpartyForm(forms.ModelForm):

    class Meta:
        model = Counterparty

        fields = [
            'type',
            'company_name',
            'inn',
            'last_name',
            'first_name'
        ]

        widgets = {
            'type': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'company_name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'ООО Ромашка'
                }
            ),

            'inn': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': '1234567890'
                }
            ),

            'first_name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Иван'
                }
            ),

            'last_name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Иванов'
                }
            ),
        }


    def __init__(self, *args, counterparty_type=None, **kwargs):
        super().__init__(*args, **kwargs)

        if counterparty_type == 'customer':
            self.fields.pop('company_name')
            self.fields.pop('inn')
            self.fields.pop('type')

        elif counterparty_type == 'supplier':
            self.fields.pop('first_name')
            self.fields.pop('last_name')
            self.fields.pop('type')


    def clean(self):
        cleaned_data = super().clean()

        type = cleaned_data.get('type')

        if type == 'customer':
            if not cleaned_data.get('first_name'):
                self.add_error(
                    'first_name',
                    'Введите имя клиента'
                )

            if not cleaned_data.get('last_name'):
                self.add_error(
                    'last_name',
                    'Введите фамилию клиента'
                )


        if type == 'supplier':
            if not cleaned_data.get('company_name'):
                self.add_error(
                    'company_name',
                    'Введите название компании'
                )

            if not cleaned_data.get('inn'):
                self.add_error(
                    'inn',
                    'Введите ИНН'
                )

        return cleaned_data

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'required': 'required', 'placeholder': 'Angiopharm'})
        }

class ExcelUploadForm(forms.Form):
    file = forms.FileField(label="Выберите файл Excel (.xlsx)")


class ReceiptForm(forms.ModelForm):

    class Meta:
        model = Receipt

        fields = [
            'warehouse',
            'supplier',
            'comment'
        ]

        widgets = {

            'warehouse': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'supplier': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'comment': forms.Textarea(
                attrs={
                    'rows': 3,
                    'class': 'form-control'
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # если склад не выбран — ставим первый
        if not self.instance.pk:

            first_warehouse = Warehouse.objects.first()

            if first_warehouse:
                self.fields['warehouse'].initial = first_warehouse

class ReceiptItemForm(forms.ModelForm):

    balance = forms.DecimalField(
        required=False,
        disabled=True,
        label="Остаток",
        widget=forms.NumberInput(
            attrs={
                'class': 'form-control'
            }
        )
    )


    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=ModelSelect2Widget(
            model=Product,
            search_fields=[
                'name__icontains',
                'sku__icontains',
                'internal_code__icontains',
            ]
        ),
        label="Товар"
    )


    class Meta:

        model = ReceiptItem

        fields = [
            'product',
            'balance',
            'quantity',
            'cost_price',
            'sale_price',
        ]


        widgets = {

            'quantity': forms.NumberInput(
                attrs={
                    'class':'form-control',
                    'min':1
                }
            ),

            'cost_price': forms.NumberInput(
                attrs={
                    'class':'form-control',
                    'step':'0.01'
                }
            ),

            'sale_price': forms.NumberInput(
                attrs={
                    'class':'form-control',
                    'step':'0.01'
                }
            )
        }


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)


        # БЕЗОПАСНАЯ ПРОВЕРКА
        product = None

        if self.instance and self.instance.pk:

            product = getattr(
                self.instance,
                'product',
                None
            )


        if product:

            self.fields['cost_price'].initial = product.cost_price

            self.fields['sale_price'].initial = (
                product.sale_price or 0
            )


class SaleForm(forms.ModelForm):

    class Meta:

        model = Sale

        fields = [
            'warehouse',
            'customer',
            'comment'
        ]

        widgets = {

            'comment': forms.Textarea(
                attrs={
                    'rows': 3,
                    'class': 'form-control'
                }
            )

        }

class SaleItemForm(forms.ModelForm):

    balance = forms.DecimalField(
        required=False,
        disabled=True,
        label="Остаток",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control"
            }
        )
    )

    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=ModelSelect2Widget(
            model=Product,
            search_fields=[
                'name__icontains',
                'sku__icontains',
                'internal_code__icontains',
            ]
        ),
        label="Товар"
    )

    class Meta:

        model = SaleItem

        fields = [
            'product',
            "balance",
            'quantity',
            'sale_price'
        ]

        widgets = {

            'quantity': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': 1
                }
            ),

            'sale_price': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '0.01'
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            product = self.instance.product
        else:
            product = self.initial.get("product")

        if product:
            warehouse = Warehouse.objects.first()

            self.fields["balance"].initial = (
                product.get_balance(warehouse)
                if warehouse else 0
            )

            self.fields["sale_price"].initial = product.sale_price

ReceiptItemFormSet = inlineformset_factory(

    Receipt,

    ReceiptItem,

    form=ReceiptItemForm,

    extra=5,

    can_delete=True

)



SaleItemFormSet = inlineformset_factory(

    Sale,

    SaleItem,

    form=SaleItemForm,

    extra=1,

    can_delete=True

)
