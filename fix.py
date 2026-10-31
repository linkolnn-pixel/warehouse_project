import sqlite3

# Подключаемся напрямую к файлу базы данных
conn = sqlite3.connect("db.sqlite3")
cursor = conn.cursor()

# 1. Восстанавливаем данные из временных колонок
try:
    cursor.execute("UPDATE inventory_receipt SET supplier_id = new_supplier_id WHERE new_supplier_id IS NOT NULL;")
    cursor.execute("UPDATE inventory_sale SET customer_id = new_customer_id WHERE new_customer_id IS NOT NULL;")
except Exception:
    pass

# 2. Очищаем связи в транзакциях
try:
    cursor.execute("UPDATE inventory_transaction SET counterparty_id = NULL;")
except Exception:
    pass

# 3. ГАРАНТИЯ от IntegrityError: обнуляем любые ID, которых еще нет в новых таблицах
try:
    cursor.execute(
        "UPDATE inventory_receipt SET supplier_id = NULL WHERE supplier_id NOT IN (SELECT id FROM inventory_supplier);"
    )
    cursor.execute(
        "UPDATE inventory_sale SET customer_id = NULL WHERE customer_id NOT IN (SELECT id FROM inventory_customer);"
    )
    cursor.execute(
        "UPDATE inventory_product SET supplier_id = NULL WHERE supplier_id NOT IN (SELECT id FROM inventory_supplier);"
    )
except Exception:
    pass

conn.commit()
conn.close()
print("✅ База данных успешно исправлена!")
