from django.db import migrations

def migrate_counterparties(apps, schema_editor):
    Counterparty = apps.get_model('inventory', 'Counterparty')
    Supplier = apps.get_model('inventory', 'Supplier')
    Customer = apps.get_model('inventory', 'Customer')
    Receipt = apps.get_model('inventory', 'Receipt')
    Sale = apps.get_model('inventory', 'Sale')

    for cp in Counterparty.objects.all():
        if cp.type == 'supplier':
            # Создаем нового поставщика
            new_sup = Supplier.objects.create(
                company_name=cp.company_name,
                inn=cp.inn,
                is_deleted=cp.is_deleted
            )
            # Привязываем только к ВРЕМЕННОМУ полю (оно уже ссылается на Supplier)
            Receipt.objects.filter(supplier=cp).update(new_supplier=new_sup)

        elif cp.type == 'customer':
            # Создаем нового клиента
            new_cus = Customer.objects.create(
                first_name=cp.first_name,
                last_name=cp.last_name,
                is_deleted=cp.is_deleted
            )
            # Привязываем только к ВРЕМЕННОМУ полю (оно уже ссылается на Customer)
            Sale.objects.filter(customer=cp).update(new_customer=new_cus)

class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0024_customer_supplier_sale_new_customer_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_counterparties),
    ]
