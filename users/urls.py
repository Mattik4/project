from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Authentication
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    
    # Optional: Password change (useful for users)
    path('password/change/', views.CustomPasswordChangeView.as_view(), name='password_change'),
    
    # Root redirect
    path('', views.redirect_to_login, name='root_redirect'),
]