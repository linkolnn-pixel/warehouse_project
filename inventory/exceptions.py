


class InventoryError(Exception):
    """Базовый класс для всех ошибок приложения.
    Позволяет отлавливать любую ошибку разом."""
    pass


class InsufficientStockError(InventoryError):
    """Ошибка: Недостаточно товара на складе."""
    def __init__(self, product_name, available, requested):
        self.product_name = product_name
        self.available = available
        self.requested = requested
        self.message = (
            f"Недостаточно товара: {product_name}. "
            f"Доступно: {available} шт., запрошено: {requested} шт."
        )
        super().__init__(self.message)


class DocumentAlreadyPostedError(InventoryError):
    """Ошибка: Попытка провести уже проведенный документ (приход/продажу)."""
    def __init__(self, document_name, document_number):
        self.message = f"{document_name} №{document_number} уже проведен(а)."
        super().__init__(self.message)


class ExcelImportError(InventoryError):
    """Ошибка при парсинге Excel-файла."""
    pass


class InvalidQuantityError(InventoryError):
    def __init__(self, product_name):
        self.message = f"Количество товара «{product_name}» должно быть больше 0."
        super().__init__(self.message)

class InsufficientStockError(InventoryError):
    def __init__(self, product_name, balance, requested):
        self.message = (
            f"Недостаточно товара: {product_name}. "
            f"Доступно: {balance} шт., запрошено: {requested} шт."
        )
        super().__init__(self.message)