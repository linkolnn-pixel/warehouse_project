from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path(
        '',
        auth_views.LoginView.as_view(
            template_name='registration/login.html',
            redirect_authenticated_user=True
        ),
        name='login'
    ),

    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout'
    ),

    path('admin/', admin.site.urls),

    path(
        'inventory/',
        include('inventory.urls')
    ),

    path(
        'api/',
        include('inventory.api_urls')
    ),

    path(
        'select2/',
        include('django_select2.urls')
    ),
]