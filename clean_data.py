import json

print("Чтение файла...")
with open("data_backup.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Собираем ID всех существующих товаров
valid_products = {item["pk"] for item in data if item["model"] == "inventory.product"}
print(f"Найдено реальных товаров: {len(valid_products)}")

cleaned_data = []
orphans = 0

for item in data:
    # Ищем остатки складов
    if item["model"] == "inventory.stockbalance":
        product_id = item["fields"].get("product")
        # Если товара не существует — пропускаем этот остаток
        if product_id not in valid_products:
            orphans += 1
            continue

    cleaned_data.append(item)

print(f"Удалено зависших остатков (призраков): {orphans}")

# Записываем чистый файл
with open("data_backup_clean.json", "w", encoding="utf-8") as f:
    json.dump(cleaned_data, f, indent=2)
print("Готово! Создан файл data_backup_clean.json")
