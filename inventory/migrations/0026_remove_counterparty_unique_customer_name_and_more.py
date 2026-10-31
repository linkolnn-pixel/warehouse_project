import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0025_auto_20261031_0011'),  # Убедитесь, что тут имя вашей 0025 миграции
    ]

    operations = [
        # 1. Обнуляем поставщика у товаров (мы восстановим их скриптом, чтобы ничего не потерять)
        migrations.RunSQL("UPDATE inventory_product SET supplier_id = NULL;"),

        # 2. УДАЛЯЕМ старые сломанные колонки, из-за которых падал SQLite
        migrations.RemoveField(model_name='sale', name='customer'),
        migrations.RemoveField(model_name='receipt', name='supplier'),
        migrations.RemoveField(model_name='transaction', name='counterparty'),

        # 3. ХИТРОСТЬ: переименовываем временные колонки (с правильными данными) в основные
        migrations.RenameField(model_name='sale', old_name='new_customer', new_name='customer'),
        migrations.RenameField(model_name='receipt', old_name='new_supplier', new_name='supplier'),

        # 4. Применяем нужные свойства к переименованным колонкам
        migrations.AlterField(
            model_name='sale',
            name='customer',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='inventory.customer'),
        ),
        migrations.AlterField(
            model_name='receipt',
            name='supplier',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='inventory.supplier'),
        ),
        migrations.AlterField(
            model_name='product',
            name='supplier',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='supplied_products', to='inventory.supplier',
                                    verbose_name='Поставщик'),
        ),

        # 5. Завершаем очистку и удаление старой модели Counterparty
        migrations.RemoveConstraint(model_name='counterparty', name='unique_customer_name'),
        migrations.AlterModelOptions(name='customer',
                                     options={'verbose_name': 'Клиент', 'verbose_name_plural': 'Клиенты'}),
        migrations.AlterModelOptions(name='supplier',
                                     options={'verbose_name': 'Поставщик', 'verbose_name_plural': 'Поставщики'}),
        migrations.AlterField(model_name='customer', name='is_deleted',
                              field=models.BooleanField(default=False, verbose_name='Удален')),
        migrations.AlterField(model_name='supplier', name='is_deleted',
                              field=models.BooleanField(default=False, verbose_name='Удален')),
        migrations.DeleteModel(name='Counterparty'),
    ]
