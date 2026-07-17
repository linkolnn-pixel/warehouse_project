from django import forms
from .models import Transaction, Product, Warehouse, Counterparty

class InboundForm(forms.ModelForm):
    product = forms.ModelChoiceField(queryset=Product.objects.all(), label="Товар")
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.all(), label="Склад")
    counterparty = forms.ModelChoiceField(
        queryset=Counterparty.objects.filter(type='supplier'),
        required=False,
        label="Поставщик"
    )

    class Meta:
        model = Transaction
        fields = ['product', 'warehouse', 'counterparty', 'quantity', 'comment']
        labels = {'quantity': 'Количество', 'comment': 'Комментарий'}

class OutboundForm(forms.ModelForm):
    product = forms.ModelChoiceField(queryset=Product.objects.all(), label="Товар")
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.all(), label="Склад")
    counterparty = forms.ModelChoiceField(
        queryset=Counterparty.objects.filter(type='customer'),
        required=False,
        label="Клиент"
    )

    class Meta:
        model = Transaction
        fields = ['product', 'warehouse', 'counterparty', 'quantity', 'comment']
        labels = {'quantity': 'Количество', 'comment': 'Комментарий'}
