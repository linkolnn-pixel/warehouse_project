import json
import sys

print("Чтение исходного файла...")

# 1. Пробуем все популярные кодировки Windows и Linux
encodings_to_try = ["utf-8", "cp1251", "windows-1251", "utf-16"]
data = None

for enc in encodings_to_try:
    try:
        with open("data_backup.json", "r", encoding=enc) as f:
            data = json.load(f)
        print(f"Успех! Файл прочитан в кодировке: {enc}")
        break
    except Exception:
        pass

if data is None:
    print("Ошибка: не удалось прочитать файл ни в одной из ожидаемых кодировок.")
    sys.exit(1)

# 2. Ищем товары (приводим к нижнему регистру для надежности)
valid_products = {item["pk"] for item in data if item["model"].lower() == "inventory.product"}
print(f"Найдено реальных товаров: {len(valid_products)}")

cleaned_data = []
orphans = 0

for item in data:
    # Ищем остатки
    if item["model"].lower() == "inventory.stockbalance":
        product_id = item["fields"].get("product")
        if product_id not in valid_products:
            orphans += 1
            continue

    cleaned_data.append(item)

print(f"Удалено битых остатков: {orphans}")

# 3. Сохраняем в строгом UTF-8, чтобы Postgres в Docker был счастлив
with open("data_backup_clean.json", "w", encoding="utf-8") as f:
    json.dump(cleaned_data, f, indent=4, ensure_ascii=False)

print("Готово! Создан чистый файл data_backup_clean.json с правильной кодировкой.")
