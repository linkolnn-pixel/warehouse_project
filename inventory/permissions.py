from django.conf import settings
from rest_framework.permissions import BasePermission


class TestModeOrAuthenticated(BasePermission):
    """
    В тестовом режиме разрешает доступ без авторизации.
    В рабочем режиме требует авторизацию.
    """

    def has_permission(self, request, view):
        if getattr(settings, 'TEST_MODE', False):
            return True

        return bool(
            request.user and
            request.user.is_authenticated
        )