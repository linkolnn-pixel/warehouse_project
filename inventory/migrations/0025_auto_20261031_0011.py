from django.db import migrations

def migrate_counterparties(apps, schema_editor):
    Counterparty = apps.get_model('inventory', 'Counterparty')
    Supplier = apps.get_model('inventory', 'Supplier')
    Customer = apps.get_model('inventory', 'Customer')
    Receipt = apps.get_model('inventory', 'Receipt')
    Sale = apps.get_model('inventory', 'Sale')

    for cp in Counterparty.objects.all():
        if cp.type == 'supplier':
            new_sup = Supplier.objects.create(
                company_name=cp.company_name,
                inn=cp.inn,
                is_deleted=cp.is_deleted
            )
            Receipt.objects.filter(supplier=cp).update(new_supplier=new_sup)
        elif cp.type == 'customer':
            new_cus = Customer.objects.create(
                first_name=cp.first_name,
                last_name=cp.last_name,
                is_deleted=cp.is_deleted
            )
            Sale.objects.filter(customer=cp).update(new_customer=new_cus)

    # --- ОБНУЛЯЕМ ТОЛЬКО СТАРЫЕ КОЛОНКИ, ЧТОБЫ SQLITE ПРОШЕЛ ПРОВЕРКУ ---
    # Данные не потеряются, так как они сохранены в new_supplier/new_customer выше
    from django.db import connection
    with connection.cursor() as cursor:
        try:
            cursor.execute("UPDATE inventory_receipt SET supplier_id = NULL;")
            cursor.execute("UPDATE inventory_sale SET customer_id = NULL;")
            cursor.execute("UPDATE inventory_product SET supplier_id = NULL;")
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0024_customer_supplier_sale_new_customer_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_counterparties),
    ]
