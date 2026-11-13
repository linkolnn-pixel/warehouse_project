from django.conf import settings
from rest_framework.permissions import BasePermission


class IsServiceOrAuthenticated(BasePermission):
    """
    Разрешает доступ:
    1. Если включен TEST_MODE.
    2. Если передан правильный межсервисный токен (X-Service-Token).
    3. Если пользователь авторизован (для браузера).
    """

    def has_permission(self, request, view):
        # 1. Тестовый режим
        if getattr(settings, "TEST_MODE", False):
            return True

        # 2. Межсервисное взаимодействие (FastAPI -> Django)
        api_key = request.headers.get("X-Service-Token")
        expected_key = getattr(settings, "SERVICE_API_KEY", None)

        if api_key and expected_key and api_key == expected_key:
            return True

        # 3. Обычная авторизация (для менеджеров/админов)
        return bool(request.user and request.user.is_authenticated)
