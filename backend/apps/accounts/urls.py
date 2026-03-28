from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_user, name='login'),
    path('signup/', views.signup_user, name='signup'),
    path('profile/', views.profile, name='profile'),
    path('settings/', views.settings, name='settings'),
    path('api/user-menu/', views.user_menu, name='user_menu'),
    path('api/logout/', views.logout_user, name='logout'),
]