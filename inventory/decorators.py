from functools import wraps
from django.conf import settings
from django.shortcuts import redirect


def test_mode_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        # В тестовом режиме авторизация не требуется
        if settings.TEST_MODE:
            return view_func(request, *args, **kwargs)

        # В рабочем режиме требуем авторизацию
        if not request.user.is_authenticated:
            return redirect('login')

        return view_func(request, *args, **kwargs)

    return wrapper