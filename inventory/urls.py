from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('inbound/', views.inbound_view, name='inbound'),
    path('outbound/', views.outbound_view, name='outbound'),
    path('report/movement/', views.movement_report, name='movement_report'),
]
