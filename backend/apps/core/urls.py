from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.index, name='index'),
    path('base/', views.base_layout, name='base'),
    path('navbar/', views.navbar, name='navbar'),
]